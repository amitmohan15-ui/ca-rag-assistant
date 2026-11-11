import sys
import json
from db_traces import get_thumbs_down_traces, get_trace_by_id, get_all_traces

def show_thumbs_down_list():
    down_traces = get_thumbs_down_traces()
    print("=" * 85)
    print("           THUMBS-DOWN TRACE REVIEW QUEUE (NEWEST FIRST)")
    print("=" * 85)
    print(f"Total Negative Feedback Traces: {len(down_traces)}\n")
    
    if not down_traces:
        print("  (No thumbs-down traces recorded yet.)")
        print("=" * 85 + "\n")
        return

    for idx, t in enumerate(down_traces, start=1):
        print(f"[{idx}] Trace #{t['trace_id']} | Feedback Time: {t['feedback_timestamp']} | Latency: {t['latency_ms']:.2f} ms")
        print(f"  • Question : {t['question']}")
        print(f"  • Answer   : {t['answer'][:160]}...")
        print(f"  • Sources  :")
        for s in t.get("sources", []):
            print(f"      - {s.get('act', 'Act')} | Sec {s.get('section', 'N/A')} | Page {s.get('page', 'N/A')}")
        print("-" * 85)
    print("=" * 85 + "\n")

def show_trace_detail(trace_id: int):
    t = get_trace_by_id(trace_id)
    if not t:
        print(f"Trace #{trace_id} not found in database.")
        return

    print("=" * 85)
    print(f"                      TRACE VIEWER: RECORD #{trace_id}")
    print("=" * 85)
    print(f"Trace ID         : {t['id']}")
    print(f"Timestamp        : {t['timestamp']}")
    print(f"Execution Time   : {t['latency_ms']:.2f} ms")
    print(f"Question         : {t['question']}")
    print(f"\nGenerated Answer :")
    print(f"{t['answer']}")
    print(f"\nStructured Sources ({len(t.get('sources', []))} chunks):")
    for s in t.get("sources", []):
        print(f"  • Act: {s.get('act', 'N/A')} | Section: {s.get('section', 'N/A')} | Page: {s.get('page', 'N/A')}")
    print(f"\nFeedback History : {t.get('feedback_history', [])}")
    print("=" * 85 + "\n")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        show_trace_detail(int(sys.argv[1]))
    else:
        show_thumbs_down_list()

