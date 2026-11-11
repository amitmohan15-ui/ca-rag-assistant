# ⚖️ CA Legal Copilot — Indian Corporate Law RAG Assistant

An enterprise-grade, deterministic Retrieval-Augmented Generation (RAG) assistant for **Chartered Accountants, Company Secretaries, and Corporate Lawyers**, specializing in Indian Bare Acts (Companies Act 2013, Income-tax Act 1961, FEMA 1999).

---

## 🚀 Live Demo & Screenshots

- **Localhost Streamlit App:** `http://localhost:8501`
- **FastAPI Backend:** `http://localhost:8000` (Docs at `/docs`)
- **Telemetry & Feedback Server:** `http://localhost:8080`

---

## 🛠️ Key Capabilities & Architecture

1. **Bare Act Section-Aware Chunking:**
   - Chunks legal text along statutory section boundaries (`185. Loans to directors`, `177. Audit Committee`).
   - Handles large sections with 800-token chunks and 100-token overlaps using `tiktoken`.
   - Embeds rich statutory metadata: Act name, year, chapter, section number, title, page.

2. **Hybrid Search with Reciprocal Rank Fusion (RRF):**
   - Dense Vector Retrieval via **ChromaDB**.
   - Sparse Keyword Retrieval via **BM25Okapi** (`rank_bm25`).
   - Fuses top 20 rankings with RRF ($k=60$) for legal precision.

3. **Cross-Encoder Re-Ranking:**
   - Pairs candidate chunks with the user question and scores with a local Cross-Encoder (`ms-marco-MiniLM-L-6-v2`), re-ranking top 30 candidates down to the top 5.

4. **NVIDIA NeMo Guardrails:**
   - **Input Rails:** Blocks prompt injection/jailbreak attempts and filters out-of-scope queries.
   - **Output Rails:** Verifies content safety and checks groundedness against retrieved chunks.
   - Rejects unanswerable queries with: *"I could not find this in the documents."*

5. **DeepEval Golden Set Benchmark:**
   - Evaluates 35 benchmark test cases (30 CA questions + 5 unanswerable out-of-scope questions).
   - Metrics: **Contextual Recall (97.1%)**, **Contextual Precision (97.1%)**, **Faithfulness (100%)**, and **Zero-Hallucination Refusal (100%)**.

6. **Enterprise Security & Telemetry:**
   - Role-Based Access Control (RBAC): `senior_ca` (All Acts) vs `junior_ca` (Companies Act 2013 only).
   - Daily quota cap enforced at 50 queries/day in SQLite (returns HTTP 429 when exceeded).
   - Thumbs Up / Thumbs Down feedback loop logged to `traces.db`.

---

## 📦 Quick Start & Local Run

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the Streamlit Application
```bash
streamlit run app.py
```
Open **`http://localhost:8501`** in your browser.

### 3. Run the DeepEval Benchmark
```bash
python evaluate.py
```

### 4. Run the FastAPI Enterprise Server
```bash
python server.py
```

---

## ☁️ Deploy to Streamlit Community Cloud

1. Push this repository to GitHub:
   ```bash
   git init
   git add .
   git commit -m "Deploy CA Legal Copilot"
   git branch -M main
   git remote add origin https://github.com/<YOUR_USERNAME>/ca-legal-copilot.git
   git push -u origin main
   ```
2. Go to **[share.streamlit.io](https://share.streamlit.io/)**.
3. Click **"New app"**, select your repository, set the main file path to **`app.py`**, and click **"Deploy"**!

