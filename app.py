import time
import json
import os
import streamlit as st
import pandas as pd

from rag import answer, load_knowledge_base
from db_traces import log_trace, record_feedback, get_thumbs_down_traces, get_all_traces
import evaluate

# Page Configuration
st.set_page_config(
    page_title="CA Legal Copilot — Companies Act 2013",
    page_icon="⚖️",
    layout="wide"
)

# Initialize Session State
if "messages" not in st.session_state:
    st.session_state.messages = []
if "traces_history" not in st.session_state:
    st.session_state.traces_history = {}

# Preload knowledge base
load_knowledge_base()

# Sidebar: Controls & Roles
st.sidebar.title("⚖️ CA Copilot Controls")
role = st.sidebar.selectbox("Active User Role (RBAC)", ["senior_ca (All Acts)", "junior_ca (Companies Act only)"])
st.sidebar.markdown("---")

st.sidebar.markdown("### 📌 Suggested CA Questions")
examples = [
    "What is the threshold for a company to constitute an audit committee?",
    "What are the restrictions on advancing loans to directors under Section 185?",
    "What is the net profit threshold that triggers Corporate Social Responsibility (CSR) obligations?",
    "Who is eligible to be appointed as an auditor of a company under Section 141?",
    "What is the GST rate on legal services?"
]
for ex in examples:
    if st.sidebar.button(ex, key=f"ex_{ex[:25]}"):
        st.session_state.selected_query = ex

st.sidebar.markdown("---")
st.sidebar.info("💡 **Grounded on Companies Act, 2013.** Cites exact Section, Title, Chapter, and Page numbers. Refuses out-of-scope non-Act queries.")

# Main Application Tabs
tab_chat, tab_benchmark, tab_feedback, tab_search = st.tabs([
    "💬 Advisory Chatbot", 
    "📈 DeepEval Benchmark Scorecard", 
    "👎 Negative Feedback Queue", 
    "📖 Bare Act Search"
])

# ---------------------------------------------------------------------------
# TAB 1: Advisory Chatbot
# ---------------------------------------------------------------------------
with tab_chat:
    st.header("⚖️ Chartered Accountant AI Legal Assistant")
    st.caption("Ask compliance, governance, and statutory questions grounded on the Companies Act, 2013.")

    # Display conversation history
    for idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
            # Show thumbs up / down feedback buttons for assistant messages
            if msg["role"] == "assistant" and "trace_id" in msg:
                trace_id = msg["trace_id"]
                col_up, col_down, col_status = st.columns([1, 1, 8])
                with col_up:
                    if st.button("👍 Up", key=f"up_{idx}_{trace_id}"):
                        record_feedback(trace_id, "up")
                        st.toast(f"Recorded Thumbs Up for Trace #{trace_id}!", icon="👍")
                with col_down:
                    if st.button("👎 Down", key=f"down_{idx}_{trace_id}"):
                        record_feedback(trace_id, "down")
                        st.toast(f"Recorded Thumbs Down for Trace #{trace_id}!", icon="👎")

            # Expandable sources
            if "sources" in msg and msg["sources"]:
                with st.expander("📚 Retrieved Statutory Chunks & Citations"):
                    for s_idx, s in enumerate(msg["sources"], 1):
                        st.markdown(f"**{s_idx}. {s.get('citation')}**")
                        st.caption(f"Chapter: {s.get('metadata', {}).get('chapter', 'N/A')} | Page: {s.get('metadata', {}).get('page', 'N/A')}")
                        st.text(s.get("text", "")[:300] + "...")

    # Query Input
    query_input = st.chat_input("Enter your Companies Act or corporate governance query...")
    
    # Handle suggested queries from sidebar click
    if "selected_query" in st.session_state and st.session_state.selected_query:
        query_input = st.session_state.selected_query
        st.session_state.selected_query = None

    if query_input:
        st.session_state.messages.append({"role": "user", "content": query_input})
        with st.chat_message("user"):
            st.markdown(query_input)

        with st.chat_message("assistant"):
            with st.spinner("Retrieving provisions & verifying citations..."):
                t0 = time.perf_counter()
                ans, chunks = answer(query_input, top_k=5)
                latency_ms = (time.perf_counter() - t0) * 1000

                # Log trace to SQLite
                trace_id = log_trace(query_input, ans, chunks, latency_ms)

                st.markdown(ans)
                st.caption(f"⏱️ Latency: {latency_ms:.1f} ms | Trace #{trace_id}")

                if chunks:
                    with st.expander("📚 Retrieved Statutory Chunks & Citations"):
                        for s_idx, s in enumerate(chunks, 1):
                            st.markdown(f"**{s_idx}. {s.get('citation')}**")
                            st.caption(f"Chapter: {s.get('metadata', {}).get('chapter', 'N/A')} | Page: {s.get('metadata', {}).get('page', 'N/A')}")
                            st.text(s.get("text", "")[:300] + "...")

        st.session_state.messages.append({
            "role": "assistant",
            "content": ans,
            "trace_id": trace_id,
            "sources": chunks,
            "latency_ms": latency_ms
        })
        st.rerun()

# ---------------------------------------------------------------------------
# TAB 2: DeepEval Benchmark Scorecard
# ---------------------------------------------------------------------------
with tab_benchmark:
    st.header("📈 DeepEval Golden Set Benchmark (35 Test Cases)")
    st.markdown("Evaluates Contextual Recall, Contextual Precision, Faithfulness, Relevancy, and Refusal Accuracy.")
    
    if st.button("🚀 Re-Run Golden Set Benchmark", type="primary"):
        with st.spinner("Evaluating 35 questions..."):
            evaluate.evaluate_golden_set("golden_set.csv", "eval_results.json")
            st.success("Evaluation complete!")

    if os.path.exists("eval_results.json"):
        with open("eval_results.json", "r", encoding="utf-8") as f:
            eval_data = json.load(f)
        
        df_eval = pd.DataFrame(eval_data)
        
        kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
        kpi1.metric("Contextual Recall", f"{df_eval['contextual_recall'].mean()*100:.1f}%")
        kpi2.metric("Contextual Precision", f"{df_eval['contextual_precision'].mean()*100:.1f}%")
        kpi3.metric("Faithfulness", f"{df_eval['faithfulness'].mean()*100:.1f}%")
        kpi4.metric("Answer Relevancy", f"{df_eval['answer_relevancy'].mean()*100:.1f}%")
        kpi5.metric("Avg Latency", f"{df_eval['latency_seconds'].mean():.3f}s")

        st.markdown("---")
        st.subheader("Per-Question Test Case Results")
        display_cols = ["id", "question", "answerable", "contextual_recall", "contextual_precision", "faithfulness", "source_cited", "refused_correctly", "latency_seconds"]
        st.dataframe(df_eval[[c for c in display_cols if c in df_eval.columns]], use_container_width=True)

# ---------------------------------------------------------------------------
# TAB 3: Thumbs-Down Feedback Queue
# ---------------------------------------------------------------------------
with tab_feedback:
    st.header("👎 Negative Feedback Review Queue")
    st.caption("Review flagged answers for root-cause analysis (retrieval miss, generation miss, or citation miss).")

    down_traces = get_thumbs_down_traces()
    if not down_traces:
        st.info("No thumbs-down traces recorded yet.")
    else:
        st.write(f"Total Negative Feedback Records: **{len(down_traces)}**")
        for t in down_traces:
            with st.container():
                st.markdown(f"### 🚩 Trace #{t['trace_id']} — Flagged on `{t['feedback_timestamp']}`")
                st.markdown(f"**Question:** {t['question']}")
                st.markdown(f"**Answer:** {t['answer']}")
                st.caption(f"Execution Latency: {t['latency_ms']:.1f} ms | Sources: {len(t.get('sources', []))} chunks")
                st.markdown("---")

# ---------------------------------------------------------------------------
# TAB 4: Bare Act Search
# ---------------------------------------------------------------------------
with tab_search:
    st.header("📖 Bare Act Statutory Search")
    search_q = st.text_input("Enter statutory section number or keyword (e.g. 177, 185, CSR, auditor):")
    if search_q:
        ans, chunks = answer(search_q, top_k=5)
        st.write(f"Found **{len(chunks)}** relevant statutory provisions:")
        for idx, c in enumerate(chunks, 1):
            m = c["metadata"]
            st.markdown(f"#### {idx}. Section {m.get('section_number')}: {m.get('section_title')}")
            st.markdown(f"- **Chapter:** {m.get('chapter')}")
            st.markdown(f"- **Page in Bare Act:** {m.get('page')}")
            st.markdown(f"- **Citation Label:** `{c.get('citation')}`")
            st.code(c.get("text", "")[:400] + "...")
            st.markdown("---")
