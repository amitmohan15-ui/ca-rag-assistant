import sys, os, datetime, chromadb
from pathlib import Path
import chunk, config, evaluate
from embed import get_embedding_vectors

def update_act(pdf_path: str, act_name: str):
    version_date = datetime.date.today().isoformat()
    client = chromadb.PersistentClient(path=config.CHROMA_PERSIST_DIR)
    collection = client.get_or_create_collection(config.COLLECTION_NAME, metadata={"hnsw:space": "cosine"})

    # 1. Parse PDF and chunk using existing baseline chunker
    temp_md = os.path.join("parsed", f"{Path(pdf_path).stem}.md")
    import pypdf
    reader = pypdf.PdfReader(pdf_path)
    lines = [f"# {act_name}\n"] + [f"\n<!-- Page {i+1} -->\n{p.extract_text() or ''}" for i, p in enumerate(reader.pages)]
    Path(temp_md).write_text("\n".join(lines), encoding="utf-8")

    new_chunks = chunk.process_markdown_file(temp_md, chunk.get_tokenizer())
    
    # 2. Find existing chunks for this act and set status to 'superseded' (do not delete)
    existing = collection.get(where={"act_name": act_name})
    superseded_count = len(existing["ids"]) if existing and existing["ids"] else 0
    if superseded_count > 0:
        updated_metas = []
        for meta in existing["metadatas"]:
            m = dict(meta)
            m["status"] = "superseded"
            updated_metas.append(m)
        collection.update(ids=existing["ids"], metadatas=updated_metas)

    # 3. Tag new chunks with version_date, act_name, and status="live", then index
    add_ids, add_docs, add_metas = [], [], []
    for idx, c in enumerate(new_chunks):
        c["act_name"], c["version_date"], c["status"] = act_name, version_date, "live"
        cid = f"{Path(pdf_path).stem}_v{version_date}_{c['section_number']}_{c['part']}_{idx}"
        meta = {
            "source_file": str(c.get("source_file", "")),
            "act_name": act_name,
            "version_date": version_date,
            "status": "live",
            "section_number": str(c.get("section_number", "")),
            "section_title": str(c.get("section_title", "")),
            "page": int(c.get("page", 1)),
            "part": int(c.get("part", 1))
        }
        add_ids.append(cid); add_docs.append(c["text"]); add_metas.append(meta)

    # Work in batches using existing embedding vectors
    for b in range(0, len(add_docs), config.BATCH_SIZE):
        batch_slice = slice(b, b + config.BATCH_SIZE)
        embeds = get_embedding_vectors(add_docs[batch_slice], config.EMBEDDING_PROVIDER, config.EMBEDDING_MODEL)
        collection.add(ids=add_ids[batch_slice], documents=add_docs[batch_slice], metadatas=add_metas[batch_slice], embeddings=embeds)

    # 4. Update chunks.jsonl with live status and refresh rag knowledge base
    live_chunks = [c for c in new_chunks]
    with open("chunks.jsonl", "w", encoding="utf-8") as f:
        import json
        for c in live_chunks: f.write(json.dumps(c, ensure_ascii=False) + "\n")
    
    # 5. Run golden set evaluation
    eval_res = evaluate.evaluate_golden_set("golden_set.csv", "eval_results.json")
    
    # Summary
    print("\n" + "="*60 + "\nACT VERSION UPDATE SUMMARY\n" + "="*60)
    print(f"Act Name          : {act_name}\nVersion Date      : {version_date}")
    print(f"Chunks Added      : {len(new_chunks)} (Status: live)")
    print(f"Chunks Superseded : {superseded_count} (Status: superseded)")
    print(f"Live Chunks in DB : {collection.count() - superseded_count}")
    print("="*60 + "\n")

if __name__ == "__main__":
    pdf = sys.argv[1] if len(sys.argv) > 1 else "companiesact2013.pdf"
    act = sys.argv[2] if len(sys.argv) > 2 else "Companies Act"
    update_act(pdf, act)

