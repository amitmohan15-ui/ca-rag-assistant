import http.server
import json
import time
import urllib.parse
from typing import Dict, Any

from db_traces import log_trace, record_feedback, get_thumbs_down_traces, get_trace_by_id, get_all_traces
from rag import answer

PORT = 8080

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>CA Legal Copilot - Trace & Feedback Portal</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 24px; }
        .container { max-width: 950px; margin: auto; }
        nav { display: flex; gap: 15px; margin-bottom: 25px; border-bottom: 1px solid #334155; padding-bottom: 12px; }
        nav a { color: #94a3b8; text-decoration: none; font-weight: 600; padding: 6px 12px; border-radius: 6px; cursor: pointer; }
        nav a.active { color: #38bdf8; background: #1e293b; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .card { background: #1e293b; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }
        h1, h2, h3 { color: #38bdf8; margin-top: 0; }
        input[type="text"], textarea, select { width: 100%; padding: 12px; background: #334155; border: 1px solid #475569; color: white; border-radius: 8px; box-sizing: border-box; font-size: 15px; }
        button { background: #2563eb; color: white; border: none; padding: 12px 20px; border-radius: 8px; font-weight: bold; cursor: pointer; font-size: 15px; margin-top: 10px; }
        button:hover { background: #1d4ed8; }
        .btn-thumb { background: #334155; border: 1px solid #475569; padding: 8px 14px; font-size: 14px; border-radius: 6px; cursor: pointer; margin-right: 8px; display: inline-flex; align-items: center; gap: 6px; }
        .btn-thumb:hover { background: #475569; }
        .btn-thumb.up:hover { background: #065f46; border-color: #10b981; }
        .btn-thumb.down:hover { background: #881337; border-color: #f43f5e; }
        .answer-box { background: #0f172a; padding: 16px; border-radius: 8px; border-left: 4px solid #38bdf8; margin-top: 15px; line-height: 1.6; }
        .meta-pill { display: inline-block; background: #0284c7; color: white; font-size: 12px; padding: 2px 8px; border-radius: 4px; margin-right: 6px; }
        .trace-item { border-bottom: 1px solid #334155; padding: 16px 0; }
        .trace-item:last-child { border-bottom: none; }
        .badge-down { background: #e11d48; color: white; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <nav>
            <a onclick="showTab('chat')" id="tab-link-chat" class="active">💬 Q&A & Feedback</a>
            <a onclick="showTab('review')" id="tab-link-review">👎 Thumbs-Down Review Queue</a>
            <a onclick="showTab('viewer')" id="tab-link-viewer">🔍 Full Trace Viewer</a>
        </nav>

        <!-- TAB 1: Chat with Feedback Buttons -->
        <div id="tab-chat" class="tab-content active">
            <div class="card">
                <h2>⚖️ Ask Companies Act Query</h2>
                <input type="text" id="user-question" placeholder="Enter query (e.g. What is the threshold for an audit committee under Section 177?)" value="What is the threshold for a company to constitute an audit committee?">
                <button onclick="submitQuestion()">Ask Question</button>

                <div id="result-container" style="display:none; margin-top: 20px;">
                    <div style="font-size: 13px; color: #94a3b8;">
                        <span class="meta-pill" id="trace-id-badge">Trace #</span>
                        <span class="meta-pill" id="latency-badge">Latency: 0 ms</span>
                    </div>
                    <div class="answer-box" id="answer-text"></div>
                    
                    <div style="margin-top: 15px;">
                        <span style="font-size: 14px; margin-right: 12px; color: #cbd5e1;">Rate this answer:</span>
                        <button class="btn-thumb up" id="thumb-up-btn" onclick="sendFeedback('up')">👍 Thumbs Up</button>
                        <button class="btn-thumb down" id="thumb-down-btn" onclick="sendFeedback('down')">👎 Thumbs Down</button>
                        <span id="feedback-status" style="font-size: 13px; color: #10b981; margin-left: 10px;"></span>
                    </div>

                    <div style="margin-top: 20px;">
                        <h4 style="color:#94a3b8; margin-bottom:8px;">Retrieved Sources:</h4>
                        <div id="sources-list" style="font-size: 13px; color: #cbd5e1;"></div>
                    </div>
                </div>
            </div>
        </div>

        <!-- TAB 2: Thumbs-down Review Queue -->
        <div id="tab-review" class="tab-content">
            <div class="card">
                <h2>👎 Thumbs-Down Review Queue (Newest First)</h2>
                <p style="color:#94a3b8; font-size:14px;">Review all failed or flagged answers for root-cause classification and ground truth alignment.</p>
                <button onclick="loadReviewQueue()" style="width: auto; padding: 8px 16px; margin-bottom: 15px;">🔄 Refresh Review Queue</button>
                <div id="review-list-container">Loading...</div>
            </div>
        </div>

        <!-- TAB 3: Full Trace Viewer -->
        <div id="tab-viewer" class="tab-content">
            <div class="card">
                <h2>🔍 Trace Record Inspector</h2>
                <div style="display:flex; gap: 10px;">
                    <input type="text" id="search-trace-id" placeholder="Enter Trace ID (e.g. 1)" style="flex:1;">
                    <button onclick="inspectTrace()" style="width:auto; margin-top:0;">Inspect</button>
                </div>
                <div id="trace-detail-box" style="margin-top: 20px;"></div>
            </div>
        </div>
    </div>

    <script>
        let currentTraceId = null;

        function showTab(tabName) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('nav a').forEach(el => el.classList.remove('active'));
            document.getElementById('tab-' + tabName).classList.add('active');
            document.getElementById('tab-link-' + tabName).classList.add('active');
            if (tabName === 'review') loadReviewQueue();
        }

        async function submitQuestion() {
            const q = document.getElementById('user-question').value.trim();
            if (!q) return;

            document.getElementById('result-container').style.display = 'block';
            document.getElementById('answer-text').innerText = 'Generating grounded answer...';
            document.getElementById('feedback-status').innerText = '';

            const res = await fetch('/api/ask', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({question: q})
            });
            const data = await res.json();
            currentTraceId = data.trace_id;

            document.getElementById('trace-id-badge').innerText = 'Trace #' + data.trace_id;
            document.getElementById('latency-badge').innerText = data.latency_ms.toFixed(1) + ' ms';
            document.getElementById('answer-text').innerText = data.answer;

            let sHtml = '<ul>';
            data.sources.forEach(s => {
                sHtml += `<li><b>${s.act}</b> | Sec ${s.section} | Page ${s.page}</li>`;
            });
            sHtml += '</ul>';
            document.getElementById('sources-list').innerHTML = sHtml;
        }

        async function sendFeedback(rating) {
            if (!currentTraceId) return;
            const res = await fetch('/api/feedback', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({trace_id: currentTraceId, rating: rating})
            });
            const data = await res.json();
            document.getElementById('feedback-status').innerText = `Recorded ${rating.toUpperCase()} feedback for Trace #${currentTraceId}`;
        }

        async function loadReviewQueue() {
            const res = await fetch('/api/review');
            const list = await res.json();
            const container = document.getElementById('review-list-container');
            if (!list.length) {
                container.innerHTML = '<p style="color:#94a3b8;">No thumbs-down traces recorded yet.</p>';
                return;
            }
            let html = '';
            list.forEach(t => {
                let srcStr = t.sources.map(s => `${s.act} Sec ${s.section} (p. ${s.page})`).join(', ');
                html += `
                <div class="trace-item">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span class="meta-pill">Trace #${t.trace_id}</span>
                        <span class="badge-down">👎 Thumbs Down</span>
                    </div>
                    <div style="margin-top:8px;"><b>Q:</b> ${t.question}</div>
                    <div style="margin-top:6px; color:#cbd5e1;"><b>A:</b> ${t.answer.substring(0, 180)}...</div>
                    <div style="font-size:12px; color:#94a3b8; margin-top:6px;">Sources: ${srcStr} | Latency: ${t.latency_ms.toFixed(1)}ms | Flagged: ${t.feedback_timestamp}</div>
                </div>`;
            });
            container.innerHTML = html;
        }

        async function inspectTrace() {
            const id = document.getElementById('search-trace-id').value.trim();
            if (!id) return;
            const res = await fetch('/api/trace?id=' + id);
            if (res.status === 404) {
                document.getElementById('trace-detail-box').innerHTML = '<p style="color:#f43f5e;">Trace ID not found.</p>';
                return;
            }
            const t = await res.json();
            document.getElementById('trace-detail-box').innerHTML = `
            <div class="answer-box">
                <p><b>Trace ID:</b> #${t.id} | <b>Timestamp:</b> ${t.timestamp} | <b>Latency:</b> ${t.latency_ms.toFixed(1)} ms</p>
                <p><b>Question:</b> ${t.question}</p>
                <p><b>Answer:</b> ${t.answer}</p>
                <p><b>Structured Sources:</b></p>
                <pre style="background:#1e293b; padding:10px; border-radius:6px; overflow:auto;">${JSON.stringify(t.sources, null, 2)}</pre>
                <p><b>Feedback Recorded:</b> ${JSON.stringify(t.feedback_history)}</p>
            </div>`;
        }
    </script>
</body>
</html>
"""

class TraceRequestHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        elif parsed.path == "/api/review":
            down_traces = get_thumbs_down_traces()
            self._send_json(down_traces)
        elif parsed.path == "/api/trace":
            qs = urllib.parse.parse_qs(parsed.query)
            trace_id = int(qs.get("id", [0])[0])
            trace_obj = get_trace_by_id(trace_id)
            if trace_obj:
                self._send_json(trace_obj)
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b'{"error": "Not found"}')
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        data = json.loads(body) if body else {}

        if parsed.path == "/api/ask":
            question = data.get("question", "")
            
            # Wrap answer call with time.perf_counter()
            t0 = time.perf_counter()
            ans, chunks = answer(question, top_k=5)
            latency_ms = (time.perf_counter() - t0) * 1000

            # Log to SQLite traces table
            trace_id = log_trace(question, ans, chunks, latency_ms)

            sources_summary = [
                {
                    "act": c.get("metadata", {}).get("act_name", "Companies Act"),
                    "section": str(c.get("metadata", {}).get("section_number", "")),
                    "page": int(c.get("metadata", {}).get("page", 1))
                }
                for c in chunks
            ]

            self._send_json({
                "trace_id": trace_id,
                "question": question,
                "answer": ans,
                "sources": sources_summary,
                "latency_ms": latency_ms
            })

        elif parsed.path == "/api/feedback":
            trace_id = int(data.get("trace_id", 0))
            rating = data.get("rating", "up")
            fb_id = record_feedback(trace_id, rating)
            self._send_json({"status": "recorded", "feedback_id": fb_id, "trace_id": trace_id, "rating": rating})
        else:
            self.send_response(404)
            self.end_headers()

    def _send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode("utf-8"))

def run_server():
    server = http.server.HTTPServer(("127.0.0.1", PORT), TraceRequestHandler)
    print(f"Trace & Feedback Server running at: http://127.0.0.1:{PORT}")
    server.serve_forever()

if __name__ == "__main__":
    run_server()

