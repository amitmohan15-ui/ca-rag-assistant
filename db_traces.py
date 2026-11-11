import sqlite3
import json
import datetime
import time
from typing import List, Dict, Any, Optional

DB_FILE = "traces.db"

def init_traces_db(db_path: str = DB_FILE):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 1. Traces table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS traces (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        sources_json TEXT NOT NULL,
        latency_ms REAL NOT NULL
    )
    """)
    
    # 2. Feedback table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trace_id INTEGER NOT NULL,
        rating TEXT NOT NULL CHECK(rating IN ('up', 'down')),
        timestamp TEXT NOT NULL,
        FOREIGN KEY (trace_id) REFERENCES traces(id)
    )
    """)
    conn.commit()
    conn.close()

def log_trace(
    question: str,
    answer: str,
    sources: List[Dict[str, Any]],
    latency_ms: float,
    db_path: str = DB_FILE
) -> int:
    """
    Log every question, answer, structured sources, and latency_ms.
    Returns the newly inserted trace_id.
    """
    init_traces_db(db_path)
    # Normalize sources to {act, section, page}
    formatted_sources = []
    for s in sources:
        if isinstance(s, dict):
            meta = s.get("metadata", s)
            formatted_sources.append({
                "act": meta.get("act_name", "Companies Act"),
                "section": str(meta.get("section_number", "")),
                "page": int(meta.get("page", 1))
            })
        else:
            formatted_sources.append({"act": "Companies Act", "section": str(s), "page": 1})

    now_iso = datetime.datetime.now().isoformat()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO traces (timestamp, question, answer, sources_json, latency_ms)
    VALUES (?, ?, ?, ?, ?)
    """, (now_iso, question, answer, json.dumps(formatted_sources), latency_ms))
    trace_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return trace_id

def record_feedback(trace_id: int, rating: str, db_path: str = DB_FILE) -> int:
    """
    Record user feedback ('up' or 'down') for a given trace_id.
    """
    init_traces_db(db_path)
    rating_clean = rating.lower().strip()
    if rating_clean not in ("up", "down"):
        raise ValueError("Rating must be 'up' or 'down'")
    
    now_iso = datetime.datetime.now().isoformat()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO feedback (trace_id, rating, timestamp)
    VALUES (?, ?, ?)
    """, (trace_id, rating_clean, now_iso))
    feedback_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return feedback_id

def get_thumbs_down_traces(db_path: str = DB_FILE) -> List[Dict[str, Any]]:
    """
    Query all thumbs-down traces with question, answer and sources, newest first.
    """
    init_traces_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
    SELECT 
        t.id AS trace_id,
        t.timestamp AS trace_timestamp,
        t.question,
        t.answer,
        t.sources_json,
        t.latency_ms,
        f.id AS feedback_id,
        f.rating,
        f.timestamp AS feedback_timestamp
    FROM feedback f
    JOIN traces t ON f.trace_id = t.id
    WHERE f.rating = 'down'
    ORDER BY f.timestamp DESC
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    for r in rows:
        try:
            r["sources"] = json.loads(r["sources_json"])
        except Exception:
            r["sources"] = []
    return rows

def get_trace_by_id(trace_id: int, db_path: str = DB_FILE) -> Optional[Dict[str, Any]]:
    """
    Retrieve full trace record and any associated feedback.
    """
    init_traces_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM traces WHERE id = ?", (trace_id,))
    trace_row = cursor.fetchone()
    if not trace_row:
        conn.close()
        return None
    
    trace_dict = dict(trace_row)
    try:
        trace_dict["sources"] = json.loads(trace_dict["sources_json"])
    except Exception:
        trace_dict["sources"] = []
        
    cursor.execute("SELECT rating, timestamp FROM feedback WHERE trace_id = ? ORDER BY id DESC", (trace_id,))
    feedbacks = [dict(f) for f in cursor.fetchall()]
    trace_dict["feedback_history"] = feedbacks
    conn.close()
    return trace_dict

def get_all_traces(limit: int = 50, db_path: str = DB_FILE) -> List[Dict[str, Any]]:
    init_traces_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM traces ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    for r in rows:
        try:
            r["sources"] = json.loads(r["sources_json"])
        except Exception:
            r["sources"] = []
    return rows

# Initialize on import
init_traces_db()

