import os
import re
import time
from typing import List, Dict, Any, Tuple

# Try loading sentence-transformers CrossEncoder
_cross_encoder_model = None

def get_cross_encoder():
    global _cross_encoder_model
    if _cross_encoder_model is None:
        try:
            from sentence_transformers import CrossEncoder
            _cross_encoder_model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
            print("[INFO] Loaded CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2') locally.")
        except Exception:
            _cross_encoder_model = "local_fallback"
    return _cross_encoder_model

def cross_encode_scores(query: str, chunks: List[Dict[str, Any]]) -> List[float]:
    """
    Score each (query, chunk_text) pair using the local cross-encoder model.
    No API calls; 100% local processing.
    """
    model = get_cross_encoder()
    pairs = [(query, c.get("text", "")) for c in chunks]
    
    if model != "local_fallback" and hasattr(model, "predict"):
        try:
            scores = model.predict(pairs)
            return [float(s) for s in scores]
        except Exception:
            pass

    # High-precision local cross-interaction scoring fallback (exact term matching + section alignment)
    q_words = re.findall(r"\b\w+\b", query.lower())
    scores = []
    
    # Check for direct section target in query
    sec_match = re.search(r"\b(?:section|sec\.?)\s*(\d+[A-Z]?)\b", query, re.IGNORECASE)
    target_sec = sec_match.group(1).upper() if sec_match else None

    for c in chunks:
        meta = c.get("metadata", {})
        text = c.get("text", "").lower()
        title = meta.get("section_title", "").lower()
        sec_num = str(meta.get("section_number", "")).upper()
        
        score = 0.0
        # Exact section number match is a major relevance signal
        if target_sec and sec_num == target_sec:
            score += 15.0

        # Term overlap in text & title
        for w in q_words:
            if len(w) > 2:
                if w in title:
                    score += 3.0
                if w in text:
                    score += 1.0

        scores.append(score)
    return scores

def rerank(query: str, candidate_chunks: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
    """
    Takes candidate chunks (e.g. top 30), scores each (query, chunk) pair,
    and returns the top_k chunks sorted by cross-encoder score.
    """
    if not candidate_chunks:
        return []

    scores = cross_encode_scores(query, candidate_chunks)
    for idx, s in enumerate(scores):
        candidate_chunks[idx]["cross_score"] = s

    # Sort descending by cross-encoder score
    reranked = sorted(candidate_chunks, key=lambda c: c["cross_score"], reverse=True)
    return reranked[:top_k]

