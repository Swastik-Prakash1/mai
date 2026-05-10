"""Code execution sandbox with blocklist and timeout.

Failure contract:
- TIMEOUT: subprocess exceeds 10s → error_code="TIMEOUT"
- EXEC_ERROR: exit_code != 0 → success=False, still return stdout/stderr
- MALFORMED: blocked import detected → reject without executing
"""

from __future__ import annotations

import asyncio
import re
import subprocess
import sys
import tempfile
import time

from tools.base import BaseTool, ToolResult

# Patterns that indicate dangerous operations
BLOCKED_PATTERNS: list[str] = [
    r"\bos\.system\b",
    r"\bsubprocess\b",
    r"\bshutil\.rmtree\b",
    r"\bopen\s*\([^)]*['\"]w['\"]",       # open(..., 'w')
    r"\bopen\s*\([^)]*['\"]a['\"]",       # open(..., 'a')
    r"\b__import__\b",
    r"\bexec\s*\(",
    r"\beval\s*\(",
]


def _check_blocklist(code: str) -> str | None:
    """Check code for blocked patterns. Returns the matched pattern or None."""
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, code):
            return pattern
    return None


class CodeExecTool(BaseTool):
    """Python code execution sandbox.

    Runs Python snippets in a subprocess with a 10-second timeout.
    Blocks dangerous imports/operations before execution.

    Failure contract:
    - TIMEOUT: subprocess.TimeoutExpired
    - EXEC_ERROR: exit_code != 0 (still returns stdout/stderr)
    - MALFORMED: blocked import/operation detected
    """

    name: str = "code_exec"

    async def call(self, input: dict) -> ToolResult:
        if "code" not in input:
            return ToolResult(
                success=False,
                error_code="MALFORMED",
                error_message="Input dict must contain 'code' key",
            )

        code = str(input["code"]).strip()
        if not code:
            return ToolResult(
                success=False,
                error_code="MALFORMED",
                error_message="Code string is empty",
            )

        # Check blocklist before executing
        blocked = _check_blocklist(code)
        if blocked:
            return ToolResult(
                success=False,
                error_code="MALFORMED",
                error_message=f"Blocked pattern detected: {blocked}",
            )

        # Execute in subprocess with timeout
        start = time.perf_counter()
        try:
            result = await asyncio.to_thread(
                self._run_subprocess, code
            )
            return result
        except subprocess.TimeoutExpired:
            elapsed = (time.perf_counter() - start) * 1000
            return ToolResult(
                success=False,
                error_code="TIMEOUT",
                error_message="Code execution exceeded 10 second timeout",
                latency_ms=elapsed,
            )

    def _run_subprocess(self, code: str) -> ToolResult:
        """Run code in a subprocess synchronously (called from thread)."""
        start = time.perf_counter()

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as tmp:
            tmp.write(code)
            tmp.flush()
            tmp_path = tmp.name

        try:
            proc = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True,
                text=True,
                timeout=10,
            )
            elapsed = (time.perf_counter() - start) * 1000

            return ToolResult(
                success=proc.returncode == 0,
                data={
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "exit_code": proc.returncode,
                    "execution_time_ms": round(elapsed, 2),
                },
                error_code="EXEC_ERROR" if proc.returncode != 0 else None,
                error_message=proc.stderr[:500] if proc.returncode != 0 else None,
                latency_ms=elapsed,
            )
        except subprocess.TimeoutExpired:
            raise  # Let the caller handle it
