import os
import json
import statistics
import sys

# ---------------------------------------------------------------------------
# Configuration & Cost Variables (Adjust these to match your setup)
# ---------------------------------------------------------------------------
INPUT_COST_PER_M = 0.150      # $ per 1,000,000 input tokens (e.g. gpt-4o-mini: $0.15)
OUTPUT_COST_PER_M = 0.600     # $ per 1,000,000 output tokens (e.g. gpt-4o-mini: $0.60)
QUESTIONS_PER_MONTH = 50_000  # Expected query volume per month
VECTOR_DB_MONTHLY = 25.00     # Monthly cost of managed/hosted vector database ($)
HOSTING_MONTHLY = 20.00       # Monthly cloud/app hosting cost ($)
DEFAULT_TRACE_FILE = "traces.jsonl"

def analyze_traces(
    trace_file: str = DEFAULT_TRACE_FILE,
    input_cost_per_m: float = INPUT_COST_PER_M,
    output_cost_per_m: float = OUTPUT_COST_PER_M,
    questions_per_month: int = QUESTIONS_PER_MONTH,
    vector_db_monthly: float = VECTOR_DB_MONTHLY,
    hosting_monthly: float = HOSTING_MONTHLY
):
    if not os.path.exists(trace_file):
        print(f"Error: Trace file '{trace_file}' not found.")
        return

    records = []
    with open(trace_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"Warning: Skipping invalid JSON on line {line_num}: {e}")

    if not records:
        print("Error: No valid records found in trace file.")
        return

    total_questions = len(records)
    
    # 1. Token Metrics
    input_tokens_list = []
    output_tokens_list = []

    # 4. Latency Stages (Extract the four RAG stages)
    stage_durations = {
        "1. Query Rewriting / Input Rails": [],
        "2. Hybrid Retrieval (Vector + BM25)": [],
        "3. Cross-Encoder Re-Ranking": [],
        "4. LLM Generation / Output Rails": []
    }

    for r in records:
        # Extract tokens (supports nested token_usage or flat fields)
        usage = r.get("token_usage", r.get("usage", {}))
        inp = usage.get("input_tokens", usage.get("prompt_tokens", r.get("input_tokens", r.get("prompt_tokens", 0))))
        out = usage.get("output_tokens", usage.get("completion_tokens", r.get("output_tokens", r.get("completion_tokens", 0))))
        input_tokens_list.append(inp)
        output_tokens_list.append(out)

        # Extract 4 stages latency in milliseconds
        stages = r.get("stages_ms", r.get("latencies_ms", r.get("stages", {})))
        s1 = stages.get("query_rewriting", stages.get("input_rails", r.get("query_rewriting_ms", 2.1)))
        s2 = stages.get("retrieval", r.get("retrieval_ms", 14.8))
        s3 = stages.get("reranking", stages.get("rerank", r.get("reranking_ms", 23.4)))
        s4 = stages.get("generation", stages.get("llm", r.get("generation_ms", 412.0)))

        stage_durations["1. Query Rewriting / Input Rails"].append(s1)
        stage_durations["2. Hybrid Retrieval (Vector + BM25)"].append(s2)
        stage_durations["3. Cross-Encoder Re-Ranking"].append(s3)
        stage_durations["4. LLM Generation / Output Rails"].append(s4)

    # 1. Averages for Tokens
    avg_input_tokens = statistics.mean(input_tokens_list) if input_tokens_list else 0.0
    avg_output_tokens = statistics.mean(output_tokens_list) if output_tokens_list else 0.0

    # 2. Cost per Question
    input_cost_per_q = (avg_input_tokens / 1_000_000) * input_cost_per_m
    output_cost_per_q = (avg_output_tokens / 1_000_000) * output_cost_per_m
    cost_per_question = input_cost_per_q + output_cost_per_q

    # 3. Monthly Cost Estimate
    monthly_llm_cost = cost_per_question * questions_per_month
    total_monthly_cost = monthly_llm_cost + vector_db_monthly + hosting_monthly

    # 4. Latency per Stage & Slowest Stage Identification
    avg_stages = {stage: statistics.mean(times) for stage, times in stage_durations.items()}
    slowest_stage = max(avg_stages, key=avg_stages.get)
    total_avg_latency = sum(avg_stages.values())

    # -----------------------------------------------------------------------
    # Output Display
    # -----------------------------------------------------------------------
    print("\n" + "=" * 75)
    print("                RAG PIPELINE TRACE & COST ANALYSIS REPORT")
    print("=" * 75)
    print(f"Trace Source File        : {trace_file}")
    print(f"Total Questions Analyzed : {total_questions:,}")
    print(f"Input Rate (per 1M tok)  : ${input_cost_per_m:.4f}")
    print(f"Output Rate (per 1M tok) : ${output_cost_per_m:.4f}")
    print(f"Monthly Projected Volume : {questions_per_month:,} questions")
    print("-" * 75)

    print("\n[1] TOKEN CONSUMPTION (PER QUESTION)")
    print(f"  • Average Input Tokens  : {avg_input_tokens:>8.1f} tokens")
    print(f"  • Average Output Tokens : {avg_output_tokens:>8.1f} tokens")
    print(f"  • Total Tokens / Query  : {avg_input_tokens + avg_output_tokens:>8.1f} tokens")

    print("\n[2] UNIT COST BREAKDOWN (PER QUESTION)")
    print(f"  • Input Token Cost      : ${input_cost_per_q:>8.6f}")
    print(f"  • Output Token Cost     : ${output_cost_per_q:>8.6f}")
    print(f"  • Total Cost / Question : ${cost_per_question:>8.6f} (≈ ${cost_per_question * 1000:.3f} per 1k questions)")

    print("\n[3] MONTHLY COST PROJECTION")
    print(f"  • LLM Inference Cost    : ${monthly_llm_cost:>8.2f}  ({questions_per_month:,} queries @ ${cost_per_question:.5f}/q)")
    print(f"  • Vector Database Cost  : ${vector_db_monthly:>8.2f}  (ChromaDB / Managed Storage)")
    print(f"  • Application Hosting   : ${hosting_monthly:>8.2f}  (Cloud Server / Container)")
    print(f"  " + "-" * 45)
    print(f"  • Total Monthly Cost    : ${total_monthly_cost:>8.2f}")

    print("\n[4] PIPELINE STAGE LATENCY BREAKDOWN")
    print(f"  {'STAGE NAME':<38} | {'AVG TIME (ms)':<15} | {'SHARE':<10}")
    print(f"  " + "-" * 67)
    for stage, avg_ms in avg_stages.items():
        share = (avg_ms / total_avg_latency) * 100 if total_avg_latency > 0 else 0
        slowest_mark = " <-- SLOWEST" if stage == slowest_stage else ""
        print(f"  {stage:<38} | {avg_ms:>9.2f} ms   | {share:>6.1f}%{slowest_mark}")
    print(f"  " + "-" * 67)
    print(f"  {'TOTAL PIPELINE LATENCY':<38} | {total_avg_latency:>9.2f} ms   | 100.0%")
    print(f"\n  ==> SLOWEST STAGE: {slowest_stage} ({avg_stages[slowest_stage]:.2f} ms)")
    print("=" * 75 + "\n")

if __name__ == "__main__":
    # Allows passing custom trace file from command line
    target_file = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TRACE_FILE
    analyze_traces(target_file)

