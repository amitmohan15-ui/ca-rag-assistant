import os
import re
import csv
import time
from typing import Dict, Any, List

from rag import retrieve_chunks, answer
from rerank import rerank

def evaluate_pipeline(use_reranker: bool = False, top_candidates: int = 30, top_final: int = 5):
    with open("golden_set.csv", "r", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("answerable", "").lower() == "yes"]

    total = len(rows)
    hits = 0
    top1_citations = 0
    total_full_time = 0.0
    total_retrieval_rerank_time = 0.0

    for r in rows:
        q = r["question"]
        src = r["expected_source"]
        sec_match = re.search(r"Sec\s*(\d+[A-Z]?)", src)
        expected_sec = sec_match.group(1).upper() if sec_match else ""

        t_full_start = time.perf_counter()

        if use_reranker:
            # 1. Retrieve top 30 chunks
            t_rr_start = time.perf_counter()
            candidates = retrieve_chunks(q, top_k=top_candidates)
            # 2. Cross-encode and re-rank to top 5
            final_chunks = rerank(q, candidates, top_k=top_final)
            retrieval_rerank_duration = time.perf_counter() - t_rr_start
        else:
            # Baseline: directly retrieve top 5
            t_rr_start = time.perf_counter()
            final_chunks = retrieve_chunks(q, top_k=top_final)
            retrieval_rerank_duration = time.perf_counter() - t_rr_start

        # Answer generation step (same prompt and model)
        ans, _ = answer(q, top_k=top_final)
        full_duration = time.perf_counter() - t_full_start

        total_full_time += full_duration
        total_retrieval_rerank_time += retrieval_rerank_duration

        # Check hits and citations
        retrieved_secs = [str(c["metadata"].get("section_number", "")).upper() for c in final_chunks]
        if expected_sec in retrieved_secs:
            hits += 1
        if retrieved_secs and retrieved_secs[0] == expected_sec:
            top1_citations += 1

    return {
        "total": total,
        "hits": hits,
        "hit_rate": (hits / total) * 100,
        "top1_citations": top1_citations,
        "citation_accuracy": (top1_citations / total) * 100,
        "avg_full_time": total_full_time / total,
        "avg_retrieval_rerank_time": total_retrieval_rerank_time / total
    }

def main():
    print("=" * 80)
    print("RUNNING GOLDEN SET BENCHMARK: WITH VS WITHOUT CROSS-ENCODER RE-RANKER")
    print("=" * 80)

    print("\n[1/2] Running Baseline (Without Re-ranker: Retrieve Top 5)...")
    baseline = evaluate_pipeline(use_reranker=False, top_final=5)
    print("Baseline run completed.")

    print("\n[2/2] Running Re-ranker Pipeline (Retrieve Top 30 -> Cross-Encoder Re-rank to Top 5)...")
    with_rr = evaluate_pipeline(use_reranker=True, top_candidates=30, top_final=5)
    print("Re-ranker run completed.")

    # Print Comparative Scorecard
    print("\n" + "=" * 85)
    print("              CROSS-ENCODER RE-RANKER BEFORE & AFTER SCORECARD")
    print("=" * 85)
    print(f"{'METRIC':<36} | {'BASELINE (Top 5)':<20} | {'WITH RE-RANKER (30 -> 5)':<22}")
    print("-" * 85)
    print(f"{'Hit Rate (Expected Sec in Top 5)':<36} | {baseline['hit_rate']:>6.2f}% ({baseline['hits']}/{baseline['total']})    | {with_rr['hit_rate']:>6.2f}% ({with_rr['hits']}/{with_rr['total']})")
    print(f"{'Citation Accuracy (Top-1 Sec Match)':<36} | {baseline['citation_accuracy']:>6.2f}% ({baseline['top1_citations']}/{baseline['total']})    | {with_rr['citation_accuracy']:>6.2f}% ({with_rr['top1_citations']}/{with_rr['total']})")
    print(f"{'Retrieval + Re-rank Latency':<36} | {baseline['avg_retrieval_rerank_time']*1000:>6.2f} ms             | {with_rr['avg_retrieval_rerank_time']*1000:>6.2f} ms")
    print(f"{'Full Request Latency':<36} | {baseline['avg_full_time']*1000:>6.2f} ms             | {with_rr['avg_full_time']*1000:>6.2f} ms")
    print("-" * 85)
    
    delta_hit = with_rr['hit_rate'] - baseline['hit_rate']
    delta_cite = with_rr['citation_accuracy'] - baseline['citation_accuracy']
    delta_time = (with_rr['avg_retrieval_rerank_time'] - baseline['avg_retrieval_rerank_time']) * 1000
    
    print(f"{'QUALITY DELTA (Hit Rate)':<36} | {'Reference':<20} | {('+' if delta_hit >= 0 else '') + f'{delta_hit:.2f}%'}")
    print(f"{'PRECISION DELTA (Citation Accuracy)':<36} | {'Reference':<20} | {('+' if delta_cite >= 0 else '') + f'{delta_cite:.2f}%'}")
    print(f"{'LATENCY OVERHEAD':<36} | {'Reference':<20} | {('+' if delta_time >= 0 else '') + f'{delta_time:.2f} ms'}")
    print("=" * 85 + "\n")

if __name__ == "__main__":
    main()

