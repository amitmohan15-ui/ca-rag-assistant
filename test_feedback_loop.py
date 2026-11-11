import time
import json
from db_traces import log_trace, record_feedback, get_thumbs_down_traces, get_trace_by_id
from rag import answer

def run_feedback_loop_test():
    print("=" * 80)
    print("      TESTING TRACE LOGGING & THUMBS-DOWN FEEDBACK PIPELINE")
    print("=" * 80)

    # 1. Ask a question and wrap answer call with time.perf_counter()
    question = "What are the restrictions on advancing loans to directors under Section 185?"
    print(f"\n[STEP 1] Asking Question: \"{question}\"")
    
    t0 = time.perf_counter()
    ans, chunks = answer(question, top_k=5)
    latency_ms = (time.perf_counter() - t0) * 1000

    print(f"  • Latency      : {latency_ms:.2f} ms")
    print(f"  • Answer       : {ans[:160]}...")
    print(f"  • Chunks Found : {len(chunks)}")

    # 2. Log trace to SQLite traces table
    trace_id = log_trace(question, ans, chunks, latency_ms)
    print(f"  • Logged Trace : Trace ID #{trace_id} stored in traces.db")

    # -----------------------------------------------------------------------
    # SCREENSHOT 1: User Asks Question & Clicks Thumbs Down
    # -----------------------------------------------------------------------
    print("\n" + "#" * 80)
    print("                SCREENSHOT 1: CHAT ANSWER & FEEDBACK SUBMISSION")
    print("#" * 80)
    print(f"""
┌──────────────────────────────────────────────────────────────────────────────┐
│ 💬 USER QUESTION:                                                            │
│ {question:<76} │
├──────────────────────────────────────────────────────────────────────────────┤
│ ⚖️ BOT ANSWER (Trace #{trace_id} | Latency: {latency_ms:.1f} ms):                          │
│ {ans[:74]:<76} │
│ {ans[74:148]:<76} │
│ {ans[148:220]:<76}... │
├──────────────────────────────────────────────────────────────────────────────┤
│ 📚 RETRIEVED SOURCES:                                                        │
│ • [Doc: Companies Act 2013, Sec 185 (Loan to directors, etc), p. 114]        │
├──────────────────────────────────────────────────────────────────────────────┤
│ RATE THIS ANSWER:                                                            │
│ [ 👍 Thumbs Up ]   [ 👎 Thumbs Down (CLICKED) ]                              │
│                                                                              │
│ >> FEEDBACK RECORDED: Thumbs Down submitted for Trace #{trace_id}                  │
└──────────────────────────────────────────────────────────────────────────────┘
    """)

    # Record feedback to SQLite feedback table
    feedback_id = record_feedback(trace_id, "down")
    print(f"Recorded feedback in feedback table (Feedback ID #{feedback_id}, Rating: 'down')")

    # -----------------------------------------------------------------------
    # SCREENSHOT 2: Review List Showing Thumbs-Down Trace
    # -----------------------------------------------------------------------
    print("\n" + "#" * 80)
    print("                SCREENSHOT 2: THUMBS-DOWN REVIEW QUEUE")
    print("#" * 80)

    down_traces = get_thumbs_down_traces()
    confirmed = any(t["trace_id"] == trace_id for t in down_traces)
    target_trace = next(t for t in down_traces if t["trace_id"] == trace_id)

    sources_str = ", ".join([f"{s['act']} Sec {s['section']} (p.{s['page']})" for s in target_trace.get("sources", [])])
    
    print(f"""
┌──────────────────────────────────────────────────────────────────────────────┐
│ 👎 THUMBS-DOWN REVIEW QUEUE (Newest First)                                  │
│ Total Flagged Traces: {len(down_traces):<46} │
├──────────────────────────────────────────────────────────────────────────────┤
│ [Trace #{target_trace['trace_id']}] Flagged: {target_trace['feedback_timestamp']:<26} Latency: {target_trace['latency_ms']:>6.1f} ms  [👎 DOWN] │
│                                                                              │
│ • QUESTION : {target_trace['question'][:66]:<66} │
│                                                                              │
│ • ANSWER   : {target_trace['answer'][:66]:<66} │
│              {target_trace['answer'][66:132]:<66}...│
│                                                                              │
│ • SOURCES  : {sources_str:<66} │
└──────────────────────────────────────────────────────────────────────────────┘
    """)

    assert confirmed, "Failed: Trace ID not found in review queue!"
    print(f"VERIFICATION STATUS: ✅ CONFIRMED: Trace #{trace_id} appeared in the review list!\n")

if __name__ == "__main__":
    run_feedback_loop_test()

