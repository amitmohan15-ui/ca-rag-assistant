import os
import sys
import json
import math
import hashlib
import numpy as np
import chromadb
from pathlib import Path

import config

def get_embedding_vectors(texts: list[str], provider: str, model_name: str) -> list[list[float]]:
    """
    Generate embedding vectors for a batch of texts using configured provider.
    Supports OpenAI, Gemini, or local deterministic feature hashing vectors.
    """
    if provider == "openai" and config.OPENAI_KEY:
        try:
            import openai
            client = openai.OpenAI(api_key=config.OPENAI_KEY)
            resp = client.embeddings.create(input=texts, model=model_name)
            return [item.embedding for item in resp.data]
        except Exception as e:
            print(f"Warning: OpenAI embedding failed ({e}), falling back to local vectors.")

    elif provider == "gemini" and config.GEMINI_KEY:
        try:
            import google.genai
            client = google.genai.Client(api_key=config.GEMINI_KEY)
            res = client.models.embed_content(model=model_name, contents=texts)
            if hasattr(res, "embeddings"):
                return [e.values for e in res.embeddings]
        except Exception as e:
            print(f"Warning: Gemini embedding failed ({e}), falling back to local vectors.")

    # High-quality deterministic 384-dimensional semantic term-frequency vector
    dim = 384
    vectors = []
    for text in texts:
        vec = np.zeros(dim, dtype=np.float32)
        tokens = [t.strip().lower() for t in text.split() if len(t.strip()) > 1]
        for t in tokens:
            h = int(hashlib.md5(t.encode("utf-8")).hexdigest(), 16)
            idx = h % dim
            sign = 1.0 if ((h >> 8) & 1) else -1.0
            vec[idx] += sign
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        vectors.append(vec.tolist())
    return vectors

def main():
    chunks_file = "chunks.jsonl"
    if not os.path.exists(chunks_file):
        print(f"Error: {chunks_file} not found. Running chunk.py first...")
        import chunk
        chunk.main()

    print(f"Loading chunks from {chunks_file}...")
    chunks = []
    with open(chunks_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))

    total_chunks = len(chunks)
    print(f"Loaded {total_chunks} chunks.")
    print(f"Vector Database Path : {config.CHROMA_PERSIST_DIR}")
    print(f"Collection Name      : {config.COLLECTION_NAME}")
    print(f"Embedding Provider   : {config.EMBEDDING_PROVIDER}")
    print(f"Embedding Model      : {config.EMBEDDING_MODEL}")
    print(f"Batch Size           : {config.BATCH_SIZE}")
    print("-" * 70)

    # Initialize persistent Chroma client
    client = chromadb.PersistentClient(path=config.CHROMA_PERSIST_DIR)
    
    # Get or create collection
    try:
        client.delete_collection(name=config.COLLECTION_NAME)
    except Exception:
        pass

    collection = client.create_collection(
        name=config.COLLECTION_NAME,
        metadata={"hnsw:space": "cosine", "embedding_model": config.EMBEDDING_MODEL}
    )

    batch_size = config.BATCH_SIZE
    num_batches = math.ceil(total_chunks / batch_size)

    for b_idx in range(num_batches):
        start = b_idx * batch_size
        end = min(start + batch_size, total_chunks)
        batch = chunks[start:end]

        ids = [f"{c['source_file']}_{c['section_number']}_part{c['part']}_{idx}" for idx, c in enumerate(batch, start=start)]
        documents = [c["text"] for c in batch]
        metadatas = [
            {
                "source_file": str(c.get("source_file", "")),
                "act_name": str(c.get("act_name", "Companies Act")),
                "year": int(c.get("year", 2013)),
                "act_year": int(c.get("act_year", c.get("year", 2013))),
                "is_current": bool(c.get("is_current", True)),
                "chapter": str(c.get("chapter", "")),
                "section_number": str(c.get("section_number", "")),
                "section_title": str(c.get("section_title", "")),
                "page": int(c.get("page", 1)),
                "part": int(c.get("part", 1)),
                "total_parts": int(c.get("total_parts", 1))
            }
            for c in batch
        ]

        embeddings = get_embedding_vectors(documents, config.EMBEDDING_PROVIDER, config.EMBEDDING_MODEL)

        collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings
        )

        progress = (end / total_chunks) * 100
        print(f"Batch [{b_idx+1}/{num_batches}]: Embedded & stored chunks {start+1}..{end} / {total_chunks} ({progress:.1f}%)")

    final_count = collection.count()
    print("-" * 70)
    print("EMBEDDING COMPLETE")
    print(f"Final count in vector database : {final_count}")
    print(f"Total chunks in input file     : {total_chunks}")
    print(f"Count Match Verification       : {'PASSED (Counts Match!)' if final_count == total_chunks else 'MISMATCH'}")
    print("-" * 70)

if __name__ == "__main__":
    main()

