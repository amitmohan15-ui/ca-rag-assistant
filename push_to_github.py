"""
Zero-dependency GitHub repository creator and code uploader.
Uploads project files directly to https://github.com/amitmohan15-ui/<repo_name>
using GitHub's REST API without requiring git CLI.
"""
import os
import base64
import json
import urllib.request
import urllib.error
import sys

GITHUB_USER = "amitmohan15-ui"
DEFAULT_REPO = "ca-rag-assistant"

INCLUDE_EXTENSIONS = {".py", ".csv", ".json", ".toml", ".md", ".txt", ".jsonl"}
EXCLUDE_DIRS = {".git", ".system_generated", "__pycache__", "chroma_db", ".pytest_cache"}
EXCLUDE_FILES = {"companiesact2013.pdf", "users_and_caps.db", "traces.db", "push_to_github.py"}

def github_api(url, data=None, token=None, method="GET"):
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Antigravity-Uploader"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8")), resp.status
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        try:
            return json.loads(err_msg), e.code
        except Exception:
            return {"message": err_msg}, e.code

def create_or_check_repo(token, repo_name):
    print(f"[*] Checking repository {GITHUB_USER}/{repo_name}...")
    repo_url = f"https://api.github.com/repos/{GITHUB_USER}/{repo_name}"
    res, status = github_api(repo_url, token=token)
    
    if status == 200:
        print(f"[+] Repository already exists: https://github.com/{GITHUB_USER}/{repo_name}")
        return True
    
    print(f"[*] Creating public repository: {repo_name}...")
    create_url = "https://api.github.com/user/repos"
    payload = {
        "name": repo_name,
        "description": "Indian Bare Acts RAG Chatbot with Streamlit UI, BM25 Hybrid Search & NeMo Guardrails",
        "private": False,
        "auto_init": False
    }
    res, status = github_api(create_url, data=payload, token=token, method="POST")
    if status in (200, 201):
        print(f"[+] Repository successfully created: https://github.com/{GITHUB_USER}/{repo_name}")
        return True
    else:
        print(f"[-] Failed to create repository: {res.get('message', res)}")
        return False

def upload_file(token, repo_name, rel_path, local_path):
    api_path = rel_path.replace("\\", "/")
    url = f"https://api.github.com/repos/{GITHUB_USER}/{repo_name}/contents/{api_path}"
    
    # Check if file exists to get SHA (for update)
    sha = None
    existing, status = github_api(url, token=token)
    if status == 200:
        sha = existing.get("sha")
    
    with open(local_path, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode("utf-8")
    
    data = {
        "message": f"Add {api_path}",
        "content": content_b64
    }
    if sha:
        data["sha"] = sha
        data["message"] = f"Update {api_path}"
    
    res, status = github_api(url, data=data, token=token, method="PUT")
    if status in (200, 201):
        print(f"  [OK] Uploaded {api_path}")
    else:
        print(f"  [ERR] {api_path}: {res.get('message', res)}")

def main():
    token = os.environ.get("GITHUB_TOKEN")
    if not token and len(sys.argv) > 1:
        token = sys.argv[1].strip()
        
    if not token:
        print("Usage: python push_to_github.py <YOUR_GITHUB_PERSONAL_ACCESS_TOKEN>")
        print("Or set the environment variable GITHUB_TOKEN.")
        print("\nGet a token at: https://github.com/settings/tokens (classic token with 'repo' scope)")
        return

    repo_name = DEFAULT_REPO
    if len(sys.argv) > 2:
        repo_name = sys.argv[2].strip()

    if not create_or_check_repo(token, repo_name):
        return

    print("\n[*] Uploading project files...")
    root_dir = os.path.dirname(os.path.abspath(__file__))
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files:
            if f in EXCLUDE_FILES:
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext in INCLUDE_EXTENSIONS or f in {".gitignore"}:
                local_path = os.path.join(root, f)
                rel_path = os.path.relpath(local_path, root_dir)
                upload_file(token, repo_name, rel_path, local_path)

    print(f"\n[DONE] Project is live on GitHub: https://github.com/{GITHUB_USER}/{repo_name}")
    print(f"Deploy on Streamlit Cloud: https://share.streamlit.io/")
    print(f"  - Repository: {GITHUB_USER}/{repo_name}")
    print(f"  - Branch: main")
    print(f"  - Main file path: app.py")

if __name__ == "__main__":
    main()

