"""Web search tool — deterministic stub with local dataset.

Failure contract:
- TIMEOUT: query > 500 characters
- EMPTY: no keyword matches found in local dataset
- MALFORMED: input dict missing "query" key
"""

from __future__ import annotations

from tools.base import BaseTool, ToolResult

# Seeded local dataset of 20 "documents" covering various topics.
# Deterministic for eval reproducibility.
SEARCH_CORPUS: list[dict] = [
    {"id": "doc_01", "title": "Merge Sort Algorithm", "url": "https://cs.example.com/merge-sort", "content": "Merge sort is a divide-and-conquer algorithm with time complexity O(n log n) in all cases. It divides the array in half, recursively sorts each half, and merges them.", "tags": ["algorithm", "sort", "merge", "complexity", "time"]},
    {"id": "doc_02", "title": "Capital Cities of Europe", "url": "https://geo.example.com/europe-capitals", "content": "Paris is the capital of France with a population of approximately 2.1 million in the city proper. Berlin is the capital of Germany. Madrid is the capital of Spain.", "tags": ["capital", "france", "paris", "europe", "city", "population"]},
    {"id": "doc_03", "title": "Prime Number Testing", "url": "https://math.example.com/primes", "content": "A prime number is a natural number greater than 1 that has no positive divisors other than 1 and itself. To check primality, test divisibility up to the square root of n.", "tags": ["prime", "number", "math", "divisor", "primality"]},
    {"id": "doc_04", "title": "Photosynthesis Explained", "url": "https://bio.example.com/photosynthesis", "content": "Photosynthesis is the biological process by which green plants convert sunlight, water, and carbon dioxide into glucose and oxygen. It occurs primarily in chloroplasts using chlorophyll.", "tags": ["photosynthesis", "biology", "plant", "chlorophyll", "sunlight"]},
    {"id": "doc_05", "title": "HTTP Protocol Overview", "url": "https://web.example.com/http", "content": "HTTP stands for HyperText Transfer Protocol. It is the foundation of data communication on the World Wide Web. HTTP defines methods like GET, POST, PUT, DELETE.", "tags": ["http", "protocol", "web", "hypertext", "transfer"]},
    {"id": "doc_06", "title": "Machine Learning Models Comparison", "url": "https://ml.example.com/models", "content": "Common ML models include linear regression, decision trees, random forests, SVMs, and neural networks. Each has different trade-offs in accuracy, interpretability, and training time.", "tags": ["model", "machine", "learning", "ml", "comparison", "neural"]},
    {"id": "doc_07", "title": "Python Performance vs Java", "url": "https://lang.example.com/python-java", "content": "Python is generally slower than Java in raw computation benchmarks. However, Python dominates ML due to libraries like NumPy, PyTorch, and TensorFlow which use optimized C/C++ backends. Python is NOT slower than Java in all benchmarks — specific numeric libraries outperform Java equivalents.", "tags": ["python", "java", "performance", "benchmark", "ml", "speed", "fast"]},
    {"id": "doc_08", "title": "Einstein's Academic Record", "url": "https://history.example.com/einstein", "content": "Contrary to popular myth, Albert Einstein did NOT fail math in school. He excelled in mathematics and physics from a young age. The myth likely arose from a misunderstanding of the Swiss grading system.", "tags": ["einstein", "math", "school", "genius", "myth", "fail", "academic"]},
    {"id": "doc_09", "title": "Global GDP Rankings 2024", "url": "https://econ.example.com/gdp-2024", "content": "The United States has the highest nominal GDP at approximately $28.8 trillion. China follows at $18.5 trillion. India's GDP is $3.9 trillion with 6.8% growth rate. Germany GDP is $4.5 trillion.", "tags": ["gdp", "economy", "growth", "country", "ranking", "india", "germany"]},
    {"id": "doc_10", "title": "India Population and Demographics", "url": "https://demo.example.com/india", "content": "India's population reached 1.44 billion in 2024, making it the most populous country. Population growth rate has slowed to 0.7% annually. The median age is 28.4 years.", "tags": ["india", "population", "demographics", "growth", "country"]},
    {"id": "doc_11", "title": "Quick Sort Analysis", "url": "https://cs.example.com/quicksort", "content": "Quick sort has an average time complexity of O(n log n) but worst case O(n^2). It is an in-place sorting algorithm. The choice of pivot significantly affects performance.", "tags": ["algorithm", "sort", "quick", "complexity", "pivot"]},
    {"id": "doc_12", "title": "Neural Network Architectures", "url": "https://ml.example.com/nn-architectures", "content": "Transformer architecture has revolutionized NLP since 2017. CNNs remain dominant for image tasks. RNNs and LSTMs are used for sequential data processing.", "tags": ["neural", "network", "transformer", "cnn", "architecture", "model"]},
    {"id": "doc_13", "title": "Climate Change Data", "url": "https://env.example.com/climate", "content": "Global average temperature has risen by approximately 1.1°C since pre-industrial times. CO2 levels reached 421 ppm in 2023. Arctic ice is declining at 13% per decade.", "tags": ["climate", "temperature", "co2", "warming", "environment"]},
    {"id": "doc_14", "title": "Stock Market Fundamentals", "url": "https://fin.example.com/stocks", "content": "The S&P 500 has historically returned about 10% annually. Diversification reduces risk. Market capitalization equals share price times outstanding shares.", "tags": ["stock", "market", "finance", "investment", "sp500"]},
    {"id": "doc_15", "title": "Data Structures Overview", "url": "https://cs.example.com/data-structures", "content": "Arrays provide O(1) access, linked lists O(1) insertion. Hash tables offer O(1) average lookup. Binary search trees provide O(log n) operations when balanced.", "tags": ["data", "structure", "array", "hash", "tree", "complexity"]},
    {"id": "doc_16", "title": "Germany Economic Profile", "url": "https://econ.example.com/germany", "content": "Germany GDP is $4.5 trillion with a population of 84 million. GDP growth rate is 0.3%. Germany is the largest economy in Europe and fourth largest globally. Population growth is slightly negative at -0.1%.", "tags": ["germany", "gdp", "economy", "population", "europe", "growth"]},
    {"id": "doc_17", "title": "Quantum Computing Basics", "url": "https://phys.example.com/quantum", "content": "Quantum computers use qubits that can exist in superposition. Quantum entanglement enables correlated measurements. Current quantum computers have 1000+ qubits.", "tags": ["quantum", "computing", "qubit", "superposition", "entanglement"]},
    {"id": "doc_18", "title": "Python Language Features", "url": "https://lang.example.com/python-features", "content": "Python supports dynamic typing, garbage collection, and multiple programming paradigms. Its extensive standard library and third-party ecosystem make it versatile.", "tags": ["python", "language", "features", "dynamic", "typing"]},
    {"id": "doc_19", "title": "Blockchain Technology", "url": "https://tech.example.com/blockchain", "content": "Blockchain is a distributed ledger technology. Bitcoin was the first blockchain application. Smart contracts enable programmable transactions on platforms like Ethereum.", "tags": ["blockchain", "bitcoin", "distributed", "ledger", "smart", "contract"]},
    {"id": "doc_20", "title": "India GDP Contradictory Source", "url": "https://econ.example.com/india-gdp-alt", "content": "India's GDP is approximately $3.5 trillion with a growth rate of 7.2%. Population growth rate is 1.1% annually. This makes India one of the fastest growing major economies.", "tags": ["india", "gdp", "economy", "growth", "population", "country"]},
]


class WebSearchTool(BaseTool):
    """Deterministic web search stub using a seeded local dataset.

    Returns up to 3 results ranked by keyword overlap relevance score.
    Designed for eval reproducibility — no external API calls.

    Failure contract:
    - TIMEOUT: if input query is >500 chars, simulate timeout
    - EMPTY: if no keyword match found in corpus
    - MALFORMED: if input dict missing "query" key
    """

    name: str = "web_search"

    async def call(self, input: dict) -> ToolResult:
        # MALFORMED: missing "query" key
        if "query" not in input:
            return ToolResult(
                success=False,
                error_code="MALFORMED",
                error_message="Input dict must contain 'query' key",
            )

        query = str(input["query"]).strip()

        # TIMEOUT: query > 500 chars
        if len(query) > 500:
            return ToolResult(
                success=False,
                error_code="TIMEOUT",
                error_message=f"Query too long ({len(query)} chars), simulated timeout",
            )

        # Score each document by keyword overlap
        query_words = set(query.lower().split())
        scored: list[tuple[float, dict]] = []

        for doc in SEARCH_CORPUS:
            tag_set = set(doc["tags"])
            content_words = set(doc["content"].lower().split())
            title_words = set(doc["title"].lower().split())

            # Overlap with tags (weighted 3x), title (2x), and content (1x)
            tag_overlap = len(query_words & tag_set)
            title_overlap = len(query_words & title_words)
            content_overlap = len(query_words & content_words)

            raw_score = tag_overlap * 3 + title_overlap * 2 + content_overlap
            if raw_score > 0:
                # Normalize to 0-1 range
                relevance = min(1.0, raw_score / (len(query_words) * 3 + 1))
                scored.append((relevance, doc))

        # EMPTY: no matches
        if not scored:
            return ToolResult(
                success=False,
                error_code="EMPTY",
                error_message=f"No results found for query: {query[:100]}",
            )

        # Sort by relevance descending, return top 3
        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for relevance, doc in scored[:3]:
            results.append({
                "title": doc["title"],
                "url": doc["url"],
                "snippet": doc["content"][:200],
                "relevance_score": round(relevance, 3),
                "doc_id": doc["id"],
            })

        return ToolResult(success=True, data={"results": results})
