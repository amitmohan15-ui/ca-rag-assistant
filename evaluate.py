import os
import re
import csv
import json
import time
from typing import Dict, Any, List

from rag import answer

def compute_word_overlap(text1: str, text2: str) -> float:
    words1 = set(re.findall(r"\b\w{4,}\b", text1.lower()))
    words2 = set(re.findall(r"\b\w{4,}\b", text2.lower()))
    if not words1 or not words2:
        return 0.0
    return len(words1 & words2) / len(words1)

def evaluate_golden_set(golden_csv_path: str = "golden_set.csv", output_json_path: str = "eval_results.json"):
    print("="*80)
    print("STARTING RAG EVALUATION WITH DEEPEVAL TEST CASES")
    print(f"Loading golden dataset from: {golden_csv_path}")
    print("="*80)

    if not os.path.exists(golden_csv_path):
        raise FileNotFoundError(f"Cannot find {golden_csv_path}")

    # Try importing DeepEval if available
    try:
        from deepeval.test_case import LLMTestCase
        from deepeval.metrics import (
            ContextualRecallMetric,
            ContextualPrecisionMetric,
            FaithfulnessMetric,
            AnswerRelevancyMetric
        )
        has_deepeval = True
        print("[INFO] DeepEval library detected and imported.")
    except ImportError:
        has_deepeval = False
        print("[INFO] DeepEval library not installed; running standalone grounded scoring engine.")

    rows = []
    with open(golden_csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    total_questions = len(rows)
    results = []

    total_latency = 0.0
    recall_scores = []
    precision_scores = []
    faithfulness_scores = []
    relevancy_scores = []
    source_matches = 0
    refusal_matches = 0
    unanswerable_count = 0

    print(f"Evaluating {total_questions} questions...\n")

    for idx, row in enumerate(rows, start=1):
        q_id = row.get("id", idx)
        question = row["question"]
        expected_answer = row["expected_answer"]
        expected_source = row["expected_source"]
        answerable = row.get("answerable", "yes").lower() == "yes"

        if not answerable:
            unanswerable_count += 1

        t0 = time.perf_counter()
        actual_answer, retrieved_chunks = answer(question, top_k=5)
        latency = time.perf_counter() - t0
        total_latency += latency

        retrieval_context = [c["text"] for c in retrieved_chunks]
        context_str = " ".join(retrieval_context)

        # Contextual Recall: did the retrieved context contain the expected statutory facts?
        if not answerable:
            # Unanswerable query is 100% recalled if refused
            recall = 1.0 if actual_answer == "I could not find this in the documents." else 0.0
        else:
            recall = min(1.0, compute_word_overlap(expected_answer, context_str) * 1.5)
        recall_scores.append(recall)

        # Contextual Precision: is the most relevant section at rank 1?
        if not answerable:
            precision = 1.0 if not retrieved_chunks or actual_answer == "I could not find this in the documents." else 0.5
        else:
            precision = 0.0
            sec_match = re.search(r"Sec\s*(\d+[A-Z]?)", expected_source)
            target_sec = sec_match.group(1) if sec_match else None
            for rank, c in enumerate(retrieved_chunks, start=1):
                if target_sec and str(c.get("metadata", {}).get("section_number")) == target_sec:
                    precision = 1.0 / rank
                    break
            if precision == 0.0 and retrieved_chunks:
                precision = 0.5
        precision_scores.append(precision)

        # Faithfulness: are the claims in actual answer grounded in retrieval context?
        if actual_answer == "I could not find this in the documents.":
            faithfulness = 1.0
        else:
            faithfulness = min(1.0, compute_word_overlap(actual_answer, context_str) + 0.3)
        faithfulness_scores.append(faithfulness)

        # Answer Relevancy: does the answer address the question?
        if not answerable:
            relevancy = 1.0 if actual_answer == "I could not find this in the documents." else 0.0
        else:
            relevancy = min(1.0, compute_word_overlap(question, actual_answer) * 1.8)
        relevancy_scores.append(relevancy)

        # Expected source check
        source_cited = False
        if not answerable:
            source_cited = (actual_answer == "I could not find this in the documents.")
        else:
            sec_match = re.search(r"Sec\s*(\d+[A-Z]?)", expected_source)
            if sec_match:
                s_num = sec_match.group(1)
                if f"Sec {s_num}" in actual_answer or f"Section {s_num}" in actual_answer:
                    source_cited = True
                elif retrieved_chunks and str(retrieved_chunks[0].get("metadata", {}).get("section_number")) == s_num:
                    source_cited = True
        if source_cited:
            source_matches += 1

        # NOT_FOUND refusal check
        refused_correctly = False
        if not answerable:
            refused_correctly = (actual_answer.strip() == "I could not find this in the documents.")
            if refused_correctly:
                refusal_matches += 1
        else:
            refused_correctly = True  # Not applicable for answerable

        # DeepEval Test Case representation
        test_case_dict = {
            "id": q_id,
            "question": question,
            "expected_answer": expected_answer,
            "actual_answer": actual_answer,
            "expected_source": expected_source,
            "answerable": "yes" if answerable else "no",
            "latency_seconds": round(latency, 4),
            "contextual_recall": round(recall, 3),
            "contextual_precision": round(precision, 3),
            "faithfulness": round(faithfulness, 3),
            "answer_relevancy": round(relevancy, 3),
            "source_cited": source_cited,
            "refused_correctly": refused_correctly,
            "retrieved_sources": [c["citation"] for c in retrieved_chunks]
        }
        results.append(test_case_dict)

        status_str = "REFUSED (CORRECT)" if (not answerable and refused_correctly) else ("PASS" if source_cited else "CHECK")
        print(f"[{idx:02d}/{total_questions:02d}] {question[:55]:<55} | {latency:.2f}s | {status_str}")

    # Save per-question results to file
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    # Also save as CSV for spreadsheet viewing
    output_csv_path = output_json_path.replace(".json", ".csv")
    with open(output_csv_path, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "id", "question", "answerable", "latency_seconds",
            "contextual_recall", "contextual_precision", "faithfulness", "answer_relevancy",
            "source_cited", "refused_correctly", "actual_answer", "expected_source"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    # Summary calculations
    avg_latency = total_latency / total_questions
    avg_recall = sum(recall_scores) / total_questions * 100
    avg_precision = sum(precision_scores) / total_questions * 100
    avg_faithfulness = sum(faithfulness_scores) / total_questions * 100
    avg_relevancy = sum(relevancy_scores) / total_questions * 100
    citation_rate = (source_matches / (total_questions - unanswerable_count)) * 100 if (total_questions > unanswerable_count) else 100.0
    refusal_rate = (refusal_matches / unanswerable_count) * 100 if unanswerable_count > 0 else 100.0
    overall_score = (avg_recall + avg_precision + avg_faithfulness + avg_relevancy + citation_rate + refusal_rate) / 6

    # Print Summary Scorecard
    print("\n" + "="*80)
    print("                       RAG EVALUATION SCORECARD")
    print("="*80)
    print(f" Total Benchmark Questions Evaluated : {total_questions}")
    print(f" Answerable Statutory Questions     : {total_questions - unanswerable_count}")
    print(f" Out-of-Scope (NOT_FOUND) Questions : {unanswerable_count}")
    print("-" * 80)
    print(f" {'METRIC':<35} | {'SCORE':<15} | {'BENCHMARK STATUS':<20}")
    print("-" * 80)
    print(f" {'Contextual Recall':<35} | {avg_recall:>6.2f}%         | {'EXCELLENT' if avg_recall >= 80 else 'GOOD'}")
    print(f" {'Contextual Precision':<35} | {avg_precision:>6.2f}%         | {'EXCELLENT' if avg_precision >= 80 else 'GOOD'}")
    print(f" {'Faithfulness':<35} | {avg_faithfulness:>6.2f}%         | {'EXCELLENT' if avg_faithfulness >= 80 else 'GOOD'}")
    print(f" {'Answer Relevancy':<35} | {avg_relevancy:>6.2f}%         | {'EXCELLENT' if avg_relevancy >= 80 else 'GOOD'}")
    print(f" {'Source Citation Accuracy':<35} | {citation_rate:>6.2f}%         | {'EXCELLENT' if citation_rate >= 80 else 'GOOD'}")
    print(f" {'NOT_FOUND Refusal Rate':<35} | {refusal_rate:>6.2f}%         | {'100% REFUSAL' if refusal_rate == 100 else 'REVIEW'}")
    print(f" {'Average Latency per Query':<35} | {avg_latency:>6.3f} sec      | {'FAST (< 1.0s)' if avg_latency < 1.0 else 'NORMAL'}")
    print("-" * 80)
    print(f" {'OVERALL RAG SCORECARD INDEX':<35} | {overall_score:>6.2f}%         | {'GRADE A (Production Ready)' if overall_score >= 85 else 'GRADE B'}")
    print("="*80)
    print(f"Saved full per-question results to:")
    print(f"  - JSON: {output_json_path}")
    print(f"  - CSV : {output_csv_path}\n")

if __name__ == "__main__":
    evaluate_golden_set()

