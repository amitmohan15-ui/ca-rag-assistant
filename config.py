import os

# Configuration for RAG system

# 1. Vector Database
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "companies_act_2013")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "64"))

# 2. Embedding Model Configuration
# Keeps the model name in configuration so questions use the exact same model later
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_KEY = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", ""))

if OPENAI_KEY:
    EMBEDDING_PROVIDER = "openai"
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")
elif GEMINI_KEY:
    EMBEDDING_PROVIDER = "gemini"
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "models/text-embedding-004")
    CHAT_MODEL = os.getenv("CHAT_MODEL", "gemini-1.5-flash")
else:
    # Local fallback using Chroma's ONNX MiniLM (works offline without any key)
    EMBEDDING_PROVIDER = "local"
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    CHAT_MODEL = os.getenv("CHAT_MODEL", "local")

TOP_K = int(os.getenv("TOP_K", "5"))
TEMPERATURE = 0.0  # Deterministic output
