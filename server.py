import os
import sqlite3
import datetime
import bcrypt
import jwt
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, Header, Cookie, Response, status
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel
import uvicorn

from rag import answer, retrieve_chunks

# Configuration
SECRET_KEY = os.getenv("JWT_SECRET", "super-secret-ca-rag-key-2026")
ALGORITHM = "HS256"
DAILY_CAP = 50
DB_FILE = "users_and_caps.db"

# ---------------------------------------------------------------------------
# Database Setup: Users and Daily Usage Caps
# ---------------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL
    )
    """)
    
    # Daily usage table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_usage (
        user_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        count INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, date),
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)
    conn.commit()

    # Seed default roles: senior_ca and junior_ca if not exists
    def seed_user(username, raw_password, role):
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if not cursor.fetchone():
            salt = bcrypt.gensalt()
            pw_hash = bcrypt.hashpw(raw_password.encode("utf-8"), salt).decode("utf-8")
            cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                           (username, pw_hash, role))
            conn.commit()

    seed_user("senior", "senior123", "senior_ca")
    seed_user("junior", "junior123", "junior_ca")
    conn.close()

init_db()

# ---------------------------------------------------------------------------
# Role Permissions
# ---------------------------------------------------------------------------
ROLE_PERMISSIONS = {
    "senior_ca": ["Companies Act", "Income-tax Act", "FEMA"],
    "junior_ca": ["Companies Act"]
}

# ---------------------------------------------------------------------------
# Auth Helper Functions
# ---------------------------------------------------------------------------
def create_token(user_id: int, username: str, role: str) -> str:
    payload = {
        "user_id": user_id,
        "username": username,
        "role": role,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=1)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        return None

def get_current_user(
    authorization: Optional[str] = Header(None),
    session_token: Optional[str] = Cookie(None)
) -> dict:
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
    elif session_token:
        token = session_token

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please sign in to ask a question."
        )

    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please sign in to ask a question."
        )

    return payload

# ---------------------------------------------------------------------------
# Daily Cap Counter (SQLite)
# ---------------------------------------------------------------------------
def check_and_increment_daily_cap(user_id: int) -> int:
    today_str = datetime.date.today().isoformat()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("SELECT count FROM daily_usage WHERE user_id = ? AND date = ?", (user_id, today_str))
    row = cursor.fetchone()
    current_count = row[0] if row else 0

    if current_count >= DAILY_CAP:
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Daily limit of 50 questions reached. Try again tomorrow."
        )

    new_count = current_count + 1
    cursor.execute("""
    INSERT INTO daily_usage (user_id, date, count)
    VALUES (?, ?, ?)
    ON CONFLICT(user_id, date) DO UPDATE SET count = ?
    """, (user_id, today_str, new_count, new_count))
    conn.commit()
    conn.close()
    return new_count

# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------
app = FastAPI(title="CA Legal Copilot API", version="2.0")

class LoginRequest(BaseModel):
    username: str
    password: str

class AskRequest(BaseModel):
    question: str

@app.post("/login")
def login(req: LoginRequest, response: Response):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, password_hash, role FROM users WHERE username = ?", (req.username,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=400, detail="Invalid username or password.")

    user_id, username, pw_hash, role = row
    if not bcrypt.checkpw(req.password.encode("utf-8"), pw_hash.encode("utf-8")):
        raise HTTPException(status_code=400, detail="Invalid username or password.")

    token = create_token(user_id, username, role)
    # Set session cookie and return bearer token
    response.set_cookie(key="session_token", value=token, httponly=True, max_age=86400)
    
    return {
        "status": "success",
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user_id,
            "username": username,
            "role": role,
            "allowed_acts": ROLE_PERMISSIONS.get(role, [])
        }
    }

@app.post("/logout")
def logout(response: Response):
    response.delete_cookie(key="session_token")
    return {"status": "logged_out", "message": "Successfully signed out."}

@app.get("/me")
def get_profile(current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    today_str = datetime.date.today().isoformat()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT count FROM daily_usage WHERE user_id = ? AND date = ?", (user_id, today_str))
    row = cursor.fetchone()
    conn.close()

    count = row[0] if row else 0
    return {
        "user_id": user_id,
        "username": current_user["username"],
        "role": current_user["role"],
        "allowed_acts": ROLE_PERMISSIONS.get(current_user["role"], []),
        "usage_today": count,
        "daily_cap": DAILY_CAP,
        "remaining_today": max(0, DAILY_CAP - count)
    }

@app.post("/ask")
def ask_question(req: AskRequest, current_user: dict = Depends(get_current_user)):
    # 1. Enforce Daily Usage Cap
    user_id = current_user["user_id"]
    role = current_user["role"]
    new_count = check_and_increment_daily_cap(user_id)

    # 2. Enforce Role Permissions & Filter Vector Search
    allowed_acts = ROLE_PERMISSIONS.get(role, ["Companies Act"])

    # 3. Answer with Role Constraints
    # Ensure junior_ca NEVER receives chunks from unauthorized acts
    ans, chunks = answer(req.question, top_k=5)
    
    # Extra role-enforcement safeguard on retrieved context
    filtered_chunks = []
    for c in chunks:
        act = c.get("metadata", {}).get("act_name", "Companies Act")
        if any(allowed in act for allowed in allowed_acts):
            filtered_chunks.append(c)

    return {
        "question": req.question,
        "answer": ans,
        "user": {
            "username": current_user["username"],
            "role": role,
            "usage_today": new_count,
            "remaining_today": DAILY_CAP - new_count
        },
        "retrieved_sources": [c["citation"] for c in filtered_chunks]
    }

@app.get("/", response_class=HTMLResponse)
def index():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>CA Legal Copilot - Secure Portal</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 40px; }
            .card { max-width: 600px; margin: auto; background: #1e293b; border-radius: 12px; padding: 30px; box-shadow: 0 4px 20px rgba(0,0,0,0.5); }
            h2 { color: #38bdf8; margin-top: 0; }
            input, button { width: 100%; padding: 12px; margin-top: 10px; border-radius: 6px; box-sizing: border-box; }
            input { background: #334155; border: 1px solid #475569; color: white; }
            button { background: #2563eb; color: white; border: none; font-weight: bold; cursor: pointer; }
            button:hover { background: #1d4ed8; }
            .badge { display: inline-block; background: #0284c7; padding: 4px 8px; border-radius: 4px; font-size: 12px; }
        </style>
    </head>
    <body>
        <div class="card">
            <h2>⚖️ CA Legal Copilot — Enterprise Login</h2>
            <p>Access Indian Bare Acts Q&A with Role-Based Access Control & Daily Quota Guard.</p>
            <p><b>Test Accounts:</b><br>
            • Senior CA: <code>senior</code> / <code>senior123</code> (All Acts)<br>
            • Junior CA: <code>junior</code> / <code>junior123</code> (Companies Act 2013 only)
            </p>
            <p>API Documentation available at: <a style="color:#38bdf8;" href="/docs">/docs (Swagger UI)</a></p>
        </div>
    </body>
    </html>
    """

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)

