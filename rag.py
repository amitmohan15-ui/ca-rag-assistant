import os
import re
import json
import math
import time
from collections import Counter
from typing import Dict, Any, List, Tuple, Optional

import config
from rerank import rerank
from guardrails import guardrails

# Global in-memory index
_chunks = None
_bm25_corpus = None
_bm25_idf = None
_bm25_avgdl = 0.0

def _tokenize(text: str) -> List[str]:
    return re.findall(r"\b\w+\b", text.lower())

def load_knowledge_base():
    global _chunks, _bm25_corpus, _bm25_idf, _bm25_avgdl
    if _chunks is not None:
        return _chunks
    
    chunks_path = "chunks.jsonl"
    if not os.path.exists(chunks_path):
        import chunk
        chunk.main()

    _chunks = []
    with open(chunks_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                _chunks.append(json.loads(line))

    # Build BM25 index over all chunks
    _bm25_corpus = [
        _tokenize(
            f"{c.get('text', '')} {c.get('section_title', '')} section {c.get('section_number', '')} {c.get('act_name', '')}"
        )
        for c in _chunks
    ]
    N = len(_bm25_corpus)
    _bm25_avgdl = sum(len(doc) for doc in _bm25_corpus) / max(1, N)
    
    df = Counter()
    for doc in _bm25_corpus:
        df.update(set(doc))
    
    _bm25_idf = {term: math.log((N - count + 0.5) / (count + 0.5) + 1.0) for term, count in df.items()}
    return _chunks

def build_citation_label(meta: dict) -> str:
    """
    Build citation label from metadata (document, section, page).
    Example: [Doc: Companies Act 2013, Sec 177, p. 108]
    """
    act_name = meta.get("act_name", "Companies Act")
    year = meta.get("act_year", meta.get("year", 2013))
    sec_num = meta.get("section_number", "")
    sec_title = meta.get("section_title", "")
    page = meta.get("page", 1)
    
    label = f"[Doc: {act_name} {year}, Sec {sec_num}"
    if sec_title:
        label += f" ({sec_title})"
    label += f", p. {page}]"
    return label

def detect_act_filter(query: str, chat_history: Optional[List[Any]] = None) -> Dict[str, Any]:
    """
    1. Metadata filter:
       Detect if question names an Act or year.
       If yes, filter to that act_name and is_current=True unless user explicitly asks for an old version.
       If no Act is named, search all current Acts (is_current=True).
    """
    q_lower = query.lower()
    
    # Check for explicit old version request
    asks_old = bool(re.search(r"\b(old|previous|prior|repealed|former|1956)\b", q_lower))
    is_current_target = not asks_old

    named_act = None
    if re.search(r"\b(companies\s*act|company\s*act|2013)\b", q_lower):
        named_act = "Companies Act"
    elif re.search(r"\b(income[\s-]*tax\s*act|it\s*act|1961)\b", q_lower):
        named_act = "Income-tax Act"
    elif re.search(r"\b(fema|foreign\s*exchange\s*management|1999)\b", q_lower):
        named_act = "FEMA"
    else:
        # Check chat history if available
        if chat_history:
            for item in reversed(chat_history):
                content = item.get("content", "") if isinstance(item, dict) else (item[0] + " " + item[1])
                c_lower = content.lower()
                if "companies act" in c_lower:
                    named_act = "Companies Act"
                    break
                elif "income-tax" in c_lower or "it act" in c_lower:
                    named_act = "Income-tax Act"
                    break
                elif "fema" in c_lower:
                    named_act = "FEMA"
                    break

    filter_dict = {"is_current": is_current_target}
    if named_act:
        filter_dict["act_name"] = named_act

    return filter_dict

def rewrite_query(question: str, chat_history: Optional[List[Any]] = None, min_words: int = 7) -> str:
    """
    2. Query rewriting:
       If the question is under min_words or is vague (e.g. 'what about section 12'),
       rewrite it into a full search query using chat history and named Act.
       Keep the original question for final answer prompt.
       Logs both original and rewritten query.
    """
    words = question.strip().split()
    is_vague = (
        len(words) < min_words or
        bool(re.match(r"^(what about|tell me about|explain|what does|how about)\b", question.strip(), re.I))
    )

    if not is_vague:
        return question

    # Infer context from chat history
    context_topic = ""
    inferred_act = "Companies Act 2013"
    
    if chat_history:
        for item in reversed(chat_history):
            content = item.get("content", "") if isinstance(item, dict) else (item[0] + " " + item[1])
            if "income-tax" in content.lower():
                inferred_act = "Income-tax Act 1961"
            elif "fema" in content.lower():
                inferred_act = "FEMA 1999"
            elif "companies act" in content.lower():
                inferred_act = "Companies Act 2013"

            # Check if there was an earlier section/topic discussed
            sec_prev = re.search(r"Section\s*(\d+[A-Z]?)", content, re.I)
            if sec_prev and not context_topic:
                context_topic = f"Section {sec_prev.group(1)}"

    # Check if section number is mentioned in the short query
    sec_match = re.search(r"\b(?:section|sec\.?)\s*(\d+[A-Z]?)\b", question, re.I)
    num_match = re.search(r"\b(\d+[A-Z]?)\b", question) if not sec_match else None
    target_sec = sec_match.group(1) if sec_match else (num_match.group(1) if num_match else None)

    if target_sec:
        rewritten = f"What are the statutory provisions, obligations, and legal rules under Section {target_sec} of the {inferred_act}?"
    elif context_topic:
        rewritten = f"{question.strip()} regarding {context_topic} under {inferred_act}"
    else:
        rewritten = f"{question.strip()} under {inferred_act}"

    print(f"\n[QUERY REWRITER]")
    print(f"  - Original Query : '{question}'")
    print(f"  - Rewritten Query: '{rewritten}'\n")

    return rewritten

def retrieve_chunks(
    question: str,
    top_k: int = 30,
    metadata_filter: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Retrieves candidate chunks filtered by act_name and is_current.
    Guarantees ZERO cross-Act contamination when an Act is filtered.
    """
    chunks = load_knowledge_base()
    q_tokens = _tokenize(question)
    
    sec_match = re.search(r"\b(?:section|sec\.?)\s*(\d+[A-Z]?)\b", question, re.I)
    boost_sec = sec_match.group(1).upper() if sec_match else None

    # Apply Metadata Filters
    target_act = metadata_filter.get("act_name") if metadata_filter else None
    target_current = metadata_filter.get("is_current") if metadata_filter else True

    k1 = 1.5
    b = 0.75
    scores = []
    
    for idx, doc in enumerate(_bm25_corpus):
        c = chunks[idx]

        # Filter on status == 'live' only
        if c.get("status", "live") != "live":
            continue

        # 1. Check act_name filter
        if target_act:
            chunk_act = str(c.get("act_name", "")).strip().lower()
            if target_act.lower() not in chunk_act:
                continue

        # 2. Check is_current filter
        if target_current is not None:
            chunk_current = bool(c.get("is_current", True))
            if chunk_current != target_current:
                continue

        doc_len = len(doc)
        doc_counts = Counter(doc)
        score = 0.0
        for token in q_tokens:
            if token in doc_counts:
                freq = doc_counts[token]
                term_idf = _bm25_idf.get(token, 0.0)
                numerator = freq * (k1 + 1.0)
                denominator = freq + k1 * (1.0 - b + b * (doc_len / _bm25_avgdl))
                score += term_idf * (numerator / denominator)
        
        # Boost exact section match
        if boost_sec and str(c.get("section_number", "")).upper() == boost_sec:
            score += 25.0

        scores.append((score, idx))

    scores.sort(reverse=True, key=lambda x: x[0])
    
    results = []
    for score, idx in scores[:top_k]:
        c = chunks[idx]
        citation = build_citation_label(c)
        results.append({
            "id": f"{c.get('source_file')}_{c.get('section_number')}_{c.get('part', 1)}",
            "text": c.get("text", ""),
            "metadata": c,
            "citation": citation,
            "score": score
        })
    return results

def call_llm(prompt: str, system_prompt: str) -> str:
    """
    Deterministic LLM caller with temperature=0.0.
    """
    if config.OPENAI_KEY:
        try:
            import openai
            client = openai.OpenAI(api_key=config.OPENAI_KEY)
            res = client.chat.completions.create(
                model=config.CHAT_MODEL if config.CHAT_MODEL != "local" else "gpt-4o-mini",
                temperature=0.0,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ]
            )
            return res.choices[0].message.content.strip()
        except Exception:
            pass

    if config.GEMINI_KEY:
        try:
            import google.genai
            client = google.genai.Client(api_key=config.GEMINI_KEY)
            full_prompt = f"{system_prompt}\n\n{prompt}"
            res = client.models.generate_content(
                model=config.CHAT_MODEL if "gemini" in config.CHAT_MODEL else "gemini-1.5-flash",
                contents=full_prompt,
                config={"temperature": 0.0}
            )
            return res.text.strip()
        except Exception:
            pass

    return ""

def generate_local_grounded_answer(question: str, top_chunks: List[Dict[str, Any]]) -> str:
    """
    Deterministic grounded answer generator when no external LLM API key is present.
    """
    if not top_chunks:
        return "I could not find this in the documents."
    
    best = top_chunks[0]
    meta = best["metadata"]
    text = best["text"]
    citation = best["citation"]

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    content_lines = []
    for l in lines:
        if l.startswith("<!--") or l.isdigit():
            continue
        content_lines.append(l)
    
    snippet = " ".join(content_lines[:6])
    if len(snippet) > 400:
        snippet = snippet[:400] + "..."

    return f"According to Section {meta.get('section_number')} ({meta.get('section_title')}), {snippet} {citation}"

def answer(
    question: str,
    top_k: int = 5,
    chat_history: Optional[List[Any]] = None
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Full RAG Pipeline with:
    1. Metadata Filtering (act_name, act_year, is_current)
    2. Query Rewriting (preserves original question for answer generation)
    3. Retrieval of 30 candidate chunks
    4. Cross-Encoder Re-ranking to top 5
    5. Deterministic Grounded Generation citing exact label
    """
    original_question = question.strip()

    # --- NeMo Guardrails Input Rail ---
    passed_input, input_refusal = guardrails.run_input_rails(original_question)
    if not passed_input:
        return input_refusal, []

    # 1. Metadata filter detection
    meta_filter = detect_act_filter(original_question, chat_history)

    # 2. Query Rewriting (logs both original and rewritten)
    search_query = rewrite_query(original_question, chat_history, min_words=7)

    # 3. Retrieve top 30 candidate chunks using filtered search
    candidate_chunks = retrieve_chunks(search_query, top_k=30, metadata_filter=meta_filter)
    if not candidate_chunks:
        return "I could not find this in the documents.", []

    # 4. Cross-Encoder Re-ranker to top 5
    final_chunks = rerank(search_query, candidate_chunks, top_k=top_k)

    # Threshold check
    if not final_chunks or final_chunks[0]["score"] < 3.0:
        return "I could not find this in the documents.", final_chunks

    # 5. Answer generation using ORIGINAL question
    context_blocks = []
    for c in final_chunks:
        context_blocks.append(f"{c['citation']}\n{c['text']}")
    context_str = "\n\n---\n\n".join(context_blocks)

    system_prompt = (
        "You are an AI Legal Assistant for Chartered Accountants specializing in Indian Bare Acts.\n"
        "Rules:\n"
        "1. Answer ONLY using information from the provided context chunks.\n"
        "2. Do NOT use outside knowledge.\n"
        "3. Cite the exact citation label (e.g. [Doc: Companies Act 2013, Sec ..., p. ...]) after EVERY claim or sentence.\n"
        "4. If the context chunks do not contain the answer, reply EXACTLY with:\n"
        "I could not find this in the documents.\n"
        "5. Keep the output deterministic."
    )

    user_prompt = f"Context Chunks:\n{context_str}\n\nQuestion: {original_question}\n\nAnswer:"
    
    llm_ans = call_llm(user_prompt, system_prompt)
    if llm_ans:
        if "could not find this in the documents" in llm_ans.lower():
            return "I could not find this in the documents.", final_chunks
        # --- NeMo Guardrails Output Rail ---
        passed_out, vetted_ans = guardrails.run_output_rails(original_question, llm_ans, final_chunks)
        return vetted_ans, final_chunks

    ans = generate_local_grounded_answer(original_question, final_chunks)
    # --- NeMo Guardrails Output Rail ---
    passed_out, vetted_ans = guardrails.run_output_rails(original_question, ans, final_chunks)
    return vetted_ans, final_chunks

if __name__ == "__main__":
    # Test short vague query rewrite
    test_short_q = "what about section 185"
    print(f"Testing short query: '{test_short_q}'")
    ans, chunks = answer(test_short_q)
    print(f"Answer: {ans[:200]}...")
    print(f"Top Citation: {chunks[0]['citation']}")
