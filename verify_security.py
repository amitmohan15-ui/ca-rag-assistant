import json
from fastapi.testclient import TestClient
from server import app, DB_FILE, DAILY_CAP
import sqlite3
import datetime

client = TestClient(app)

def test_enterprise_security():
    print("=" * 80)
    print("       FASTAPI RAG AUTH, ROLES & DAILY CAP SECURITY TEST")
    print("=" * 80)

    # Reset today's usage for clean test
    today_str = datetime.date.today().isoformat()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM daily_usage WHERE date = ?", (today_str,))
    conn.commit()
    conn.close()

    # -----------------------------------------------------------------------
    # TEST 1: Block Anonymous User (HTTP 401)
    # -----------------------------------------------------------------------
    print("\n[STEP 1] Testing Anonymous Access on POST /ask (No Token/Session)...")
    res_anon = client.post("/ask", json={"question": "What is Section 177?"})
    print(f"  HTTP Status Code : {res_anon.status_code}")
    print(f"  Response Body    : {res_anon.json()}")
    assert res_anon.status_code == 401, f"Expected 401, got {res_anon.status_code}"
    assert res_anon.json()["detail"] == "Please sign in to ask a question."
    print("  RESULT           : ✅ PASSED (HTTP 401 - Blocked Anonymous)")

    # -----------------------------------------------------------------------
    # TEST 2: Login as Junior CA
    # -----------------------------------------------------------------------
    print("\n[STEP 2] Signing in as Junior CA ('junior' / 'junior123')...")
    res_login = client.post("/login", json={"username": "junior", "password": "junior123"})
    print(f"  HTTP Status Code : {res_login.status_code}")
    login_data = res_login.json()
    token = login_data["access_token"]
    role = login_data["user"]["role"]
    allowed = login_data["user"]["allowed_acts"]
    print(f"  Role Assigned    : {role}")
    print(f"  Allowed Acts     : {allowed}")
    assert role == "junior_ca"
    assert allowed == ["Companies Act"]
    print("  RESULT           : ✅ PASSED (Logged in as junior_ca)")

    headers = {"Authorization": f"Bearer {token}"}

    # -----------------------------------------------------------------------
    # TEST 3: Ask Questions & Check Daily Cap
    # -----------------------------------------------------------------------
    print("\n[STEP 3] Testing Rate Limiting & Daily Cap (Limit = 50)...")
    print("  Simulating 50 legitimate queries...")
    for i in range(1, 51):
        r = client.post("/ask", json={"question": f"Question #{i} on Section 177"}, headers=headers)
        assert r.status_code == 200, f"Query #{i} failed with {r.status_code}"
        if i in [1, 25, 50]:
            print(f"  Query #{i:02d} -> HTTP {r.status_code} | Remaining today: {r.json()['user']['remaining_today']}")

    # -----------------------------------------------------------------------
    # TEST 4: The 51st Call (Must return HTTP 429)
    # -----------------------------------------------------------------------
    print("\n[STEP 4] Executing Question #51 (Exceeding Daily Cap of 50)...")
    res_cap = client.post("/ask", json={"question": "Question #51: Exceeding quota"}, headers=headers)
    print(f"  HTTP Status Code : {res_cap.status_code}")
    print(f"  Response Body    : {res_cap.json()}")
    assert res_cap.status_code == 429, f"Expected 429, got {res_cap.status_code}"
    assert res_cap.json()["detail"] == "Daily limit of 50 questions reached. Try again tomorrow."
    print("  RESULT           : ✅ PASSED (HTTP 429 - Daily Limit Enforced)")

    # -----------------------------------------------------------------------
    # TEST 5: Verify Senior CA Independence
    # -----------------------------------------------------------------------
    print("\n[STEP 5] Signing in as Senior CA ('senior' / 'senior123')...")
    res_senior = client.post("/login", json={"username": "senior", "password": "senior123"})
    senior_token = res_senior.json()["access_token"]
    senior_headers = {"Authorization": f"Bearer {senior_token}"}
    res_senior_ask = client.post("/ask", json={"question": "What is Section 185?"}, headers=senior_headers)
    print(f"  Senior CA HTTP Status : {res_senior_ask.status_code}")
    print(f"  Senior CA Usage Today : {res_senior_ask.json()['user']['usage_today']} / 50")
    assert res_senior_ask.status_code == 200
    print("  RESULT                : ✅ PASSED (Senior CA has independent quota)")

    print("\n" + "=" * 80)
    print("                 ALL SECURITY & QUOTA CHECKS PASSED")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    test_enterprise_security()

