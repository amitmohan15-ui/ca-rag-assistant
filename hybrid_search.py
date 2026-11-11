import os
import re
import csv
import json
import math
from typing import List, Dict, Any, Tuple

# Try importing rank_bm25; if not installed, provide exact standard BM25Okapi implementation
try:
    from rank_bm25 import BM25Okapi
except ImportError:
    class BM25Okapi:
        """
        Exact implementation of BM25Okapi from rank_bm25.
        Parameters: k1=1.5, b=0.75, epsilon=0.25
        """
        def __init__(self, corpus: List[List[str]], k1: float = 1.5, b: float = 0.75, epsilon: float = 0.25):
            self.k1 = k1
            self.b = b
            self.epsilon = epsilon
            self.corpus_size = len(corpus)
            self.doc_len = [len(x) for x in corpus]
            self.avgdl = sum(self.doc_len) / self.corpus_size if self.corpus_size > 0 else 1.0
            self.doc_freqs = []
            self.nd = {}
            for document in corpus:
                frequencies = {}
                for word in document:
                    frequencies[word] = frequencies.get(word, 0) + 1
                self.doc_freqs.append(frequencies)
                for word in frequencies:
                    self.nd[word] = self.nd.get(word, 0) + 1
            
            self.idf = {}
            idf_sum = 0.0
            negative_idfs = []
            for word, freq in self.nd.items():
                # Standard Okapi IDF
                idf = math.log((self.corpus_size - freq + 0.5) / (freq + 0.5) + 1.0)
                self.idf[word] = idf
                idf_sum += idf
                if idf < 0:
                    negative_idfs.append(word)
            
            average_idf = idf_sum / len(self.idf) if self.idf else 0.0
            eps = self.epsilon * average_idf
            for word in negative_idfs:
                self.idf[word] = eps

        def get_scores(self, query: List[str]) -> List[float]:
            scores = [0.0] * self.corpus_size
            for q in query:
                q_idf = self.idf.get(q, 0.0)
                if q_idf == 0.0:
                    continue
                for i, doc_freq in enumerate(self.doc_freqs):
                    if q in doc_freq:
                        freq = doc_freq[q]
                        numerator = freq * (self.k1 + 1.0)
                        denominator = freq + self.k1 * (1.0 - self.b + self.b * (self.doc_len[i] / self.avgdl))
                        scores[i] += q_idf * (numerator / denominator)
            return scores

# 1. Load Chunks
chunks_path = "chunks.jsonl"
if not os.path.exists(chunks_path):
    import chunk
    chunk.main()

chunks = []
with open(chunks_path, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            chunks.append(json.loads(line))

print(f"Loaded {len(chunks)} chunks.")

# 2. Tokenizer: Lowercase and split on whitespace (keeps numbers and section tokens intact)
def bm25_tokenize(text: str) -> List[str]:
    # Lowercase and split on whitespace
    return text.lower().split()

# Build BM25 index over the same chunks
tokenized_corpus = [
    bm25_tokenize(
        f"{c.get('text', '')} {c.get('section_title', '')} Section {c.get('section_number', '')} {c.get('act_name', '')}"
    )
    for c in chunks
]
bm25_index = BM25Okapi(tokenized_corpus)
print("Built BM25Okapi index successfully.")

# Initialize ChromaDB vector search
import chromadb
import config
from embed import get_embedding_vectors

chroma_client = chromadb.PersistentClient(path=config.CHROMA_PERSIST_DIR)
collection = chroma_client.get_collection(name=config.COLLECTION_NAME)

# Path A: Vector-Only Search
def vector_search(query: str, k: int = 10) -> List[Dict[str, Any]]:
    """
    Existing Vector search path (for comparison).
    Retrieves top k chunks based on vector embedding cosine similarity.
    """
    query_vec = get_embedding_vectors([query], config.EMBEDDING_PROVIDER, config.EMBEDDING_MODEL)[0]
    results = collection.query(
        query_embeddings=[query_vec],
        n_results=k,
        include=["documents", "metadatas", "distances"]
    )
    
    hits = []
    if results and results["ids"] and results["ids"][0]:
        for i in range(len(results["ids"][0])):
            doc_id = results["ids"][0][i]
            meta = results["metadatas"][0][i]
            doc = results["documents"][0][i]
            dist = results["distances"][0][i] if "distances" in results else 0.0
            hits.append({
                "id": doc_id,
                "text": doc,
                "metadata": meta,
                "score": 1.0 - dist
            })
    return hits

# BM25 Search
def bm25_search(query: str, k: int = 20) -> List[Dict[str, Any]]:
    tokenized_query = bm25_tokenize(query)
    scores = bm25_index.get_scores(tokenized_query)
    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
    
    results = []
    for rank_idx, idx in enumerate(top_indices):
        c = chunks[idx]
        doc_id = f"{c.get('source_file')}_{c.get('section_number')}_part{c.get('part', 1)}_{idx}"
        results.append({
            "id": doc_id,
            "text": c.get("text", ""),
            "metadata": c,
            "score": scores[idx]
        })
    return results

# Path B: Hybrid Search with Reciprocal Rank Fusion (RRF, k=60)
def hybrid_search(query: str, k: int = 10) -> List[Dict[str, Any]]:
    """
    Hybrid Search using Reciprocal Rank Fusion (RRF):
    RRF Score(d) = sum_{m in {vector, bm25}} (1 / (60 + r_m(d)))
    where r_m(d) is the 1-based rank in list m.
    """
    # 1. Run existing vector search, get top 20
    vector_results = vector_search(query, k=20)
    
    # 2. Run BM25, get top 20
    bm25_results = bm25_search(query, k=20)
    
    # 3. Merge both lists with Reciprocal Rank Fusion, k=60
    rrf_k = 60
    rrf_scores: Dict[str, float] = {}
    doc_lookup: Dict[str, Dict[str, Any]] = {}
    
    # Process vector rankings
    for rank_0, item in enumerate(vector_results):
        rank = rank_0 + 1  # 1-indexed rank
        doc_key = f"{item['metadata'].get('section_number')}_{item['metadata'].get('part', 1)}"
        rrf_scores[doc_key] = rrf_scores.get(doc_key, 0.0) + (1.0 / (rrf_k + rank))
        if doc_key not in doc_lookup:
            doc_lookup[doc_key] = item
            
    # Process BM25 rankings
    for rank_0, item in enumerate(bm25_results):
        rank = rank_0 + 1  # 1-indexed rank
        doc_key = f"{item['metadata'].get('section_number')}_{item['metadata'].get('part', 1)}"
        rrf_scores[doc_key] = rrf_scores.get(doc_key, 0.0) + (1.0 / (rrf_k + rank))
        if doc_key not in doc_lookup:
            doc_lookup[doc_key] = item

    # Sort merged documents by descending RRF score
    sorted_doc_keys = sorted(rrf_scores.keys(), key=lambda d: rrf_scores[d], reverse=True)[:k]
    
    # Return top k chunks with their fused RRF scores
    hybrid_top = []
    for doc_key in sorted_doc_keys:
        item = dict(doc_lookup[doc_key])
        item["rrf_score"] = rrf_scores[doc_key]
        item["score"] = rrf_scores[doc_key]
        hybrid_top.append(item)
        
    return hybrid_top

def evaluate_retrieval_on_golden_set(golden_csv_path: str = "golden_set.csv", k: int = 10):
    rows = []
    with open(golden_csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r.get("answerable", "").lower() == "yes":
                rows.append(r)

    total_answerable = len(rows)
    print(f"\nEvaluating {total_answerable} answerable golden set questions (k={k})...\n")

    vector_hits = 0
    vector_citations = 0
    
    hybrid_hits = 0
    hybrid_citations = 0

    for idx, row in enumerate(rows, start=1):
        q = row["question"]
        src = row["expected_source"]
        sec_match = re.search(r"Sec\s*(\d+[A-Z]?)", src)
        expected_sec = sec_match.group(1).upper() if sec_match else None

        # 1. Vector Search
        v_results = vector_search(q, k=k)
        v_sections = [str(r["metadata"].get("section_number", "")).upper() for r in v_results]
        v_hit = expected_sec in v_sections if expected_sec else False
        v_cite = (v_sections[0] == expected_sec) if (v_sections and expected_sec) else False
        if v_hit: vector_hits += 1
        if v_cite: vector_citations += 1

        # 2. Hybrid Search
        h_results = hybrid_search(q, k=k)
        h_sections = [str(r["metadata"].get("section_number", "")).upper() for r in h_results]
        h_hit = expected_sec in h_sections if expected_sec else False
        h_cite = (h_sections[0] == expected_sec) if (h_sections and expected_sec) else False
        if h_hit: hybrid_hits += 1
        if h_cite: hybrid_citations += 1

    v_hit_rate = (vector_hits / total_answerable) * 100
    v_cite_acc = (vector_citations / total_answerable) * 100

    h_hit_rate = (hybrid_hits / total_answerable) * 100
    h_cite_acc = (hybrid_citations / total_answerable) * 100

    return {
        "total": total_answerable,
        "vector": {"hit_rate": v_hit_rate, "citation_accuracy": v_cite_acc, "hits": vector_hits, "citations": vector_citations},
        "hybrid": {"hit_rate": h_hit_rate, "citation_accuracy": h_cite_acc, "hits": hybrid_hits, "citations": hybrid_citations}
    }

if __name__ == "__main__":
    scorecard = evaluate_retrieval_on_golden_set("golden_set.csv", k=10)
    
    v = scorecard["vector"]
    h = scorecard["hybrid"]
    tot = scorecard["total"]

    print("=" * 80)
    print("                     HYBRID SEARCH BENCHMARK SCORECARD")
    print("=" * 80)
    print("RRF Formula Used:")
    print("  RRF_Score(d) = sum_{m in {vector, bm25}} [ 1.0 / (60 + Rank_m(d)) ]")
    print(f"Total Evaluated Questions (Answerable) : {tot}")
    print("-" * 80)
    print(f"{'SEARCH METHOD':<25} | {'HIT RATE (Top-10)':<22} | {'CITATION ACCURACY (Top-1)':<25}")
    print("-" * 80)
    print(f"{'1. Vector-Only Search':<25} | {v['hit_rate']:>6.2f}% ({v['hits']}/{tot})           | {v['citation_accuracy']:>6.2f}% ({v['citations']}/{tot})")
    print(f"{'2. Hybrid Search (RRF)':<25} | {h['hit_rate']:>6.2f}% ({h['hits']}/{tot})           | {h['citation_accuracy']:>6.2f}% ({h['citations']}/{tot})")
    print("-" * 80)
    diff_hit = h['hit_rate'] - v['hit_rate']
    diff_cite = h['citation_accuracy'] - v['citation_accuracy']
    print(f"{'IMPROVEMENT DELTA':<25} | {('+' if diff_hit>=0 else '') + f'{diff_hit:.2f}%':<22} | {('+' if diff_cite>=0 else '') + f'{diff_cite:.2f}%':<25}")
    print("=" * 80)

