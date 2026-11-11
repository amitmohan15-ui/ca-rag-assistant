import os
import re
import json
import glob
from pathlib import Path
import tiktoken

def get_tokenizer():
    try:
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None

def split_tokens(text: str, tokenizer, max_tokens: int = 800, overlap: int = 100):
    """
    Split text into chunks of at most max_tokens with overlap tokens.
    """
    if tokenizer is not None:
        tokens = tokenizer.encode(text)
        if len(tokens) <= max_tokens:
            return [text]
        
        chunks = []
        step = max(1, max_tokens - overlap)
        for i in range(0, len(tokens), step):
            chunk_tokens = tokens[i : i + max_tokens]
            chunks.append(tokenizer.decode(chunk_tokens))
            if i + max_tokens >= len(tokens):
                break
        return chunks
    else:
        # Fallback word-based splitting (approx 0.75 words per token)
        words = text.split()
        max_words = int(max_tokens * 0.75)
        overlap_words = int(overlap * 0.75)
        if len(words) <= max_words:
            return [text]
        chunks = []
        step = max(1, max_words - overlap_words)
        for i in range(0, len(words), step):
            chunk_words = words[i : i + max_words]
            chunks.append(" ".join(chunk_words))
            if i + max_words >= len(words):
                break
        return chunks

def parse_pdf_if_needed(pdf_path: str = "companiesact2013.pdf", parsed_dir: str = "parsed"):
    """
    If parsed_dir is empty or missing, parse pdf_path into parsed_dir.
    """
    os.makedirs(parsed_dir, exist_ok=True)
    md_files = glob.glob(os.path.join(parsed_dir, "*.md"))
    if not md_files and os.path.exists(pdf_path):
        import pypdf
        reader = pypdf.PdfReader(pdf_path)
        base_name = Path(pdf_path).stem
        out_path = os.path.join(parsed_dir, f"{base_name}.md")
        lines = [f"# THE COMPANIES ACT, 2013\n"]
        for idx, page in enumerate(reader.pages):
            page_num = idx + 1
            lines.append(f"\n<!-- Page {page_num} -->\n")
            lines.append(page.extract_text() or "")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"Auto-parsed {pdf_path} into {out_path}")

def extract_act_metadata(filename: str, content: str):
    """
    Extract act name and year from file content or filename.
    """
    act_match = re.search(r"THE\s+([A-Z\s,]+)\s+ACT,?\s*(\d{4})", content)
    if act_match:
        act_name = f"{act_match.group(1).strip().title()} Act"
        year = int(act_match.group(2))
    else:
        stem = Path(filename).stem
        year_match = re.search(r"(\d{4})", stem)
        year = int(year_match.group(1)) if year_match else 2013
        name_only = re.sub(r"\d+", "", stem).replace("_", " ").strip().title()
        act_name = name_only if name_only else "Companies Act"
    return act_name, year

def process_markdown_file(file_path: str, tokenizer):
    content = Path(file_path).read_text(encoding="utf-8")
    filename = os.path.basename(file_path)
    act_name, year = extract_act_metadata(filename, content)

    # Split by page tags: <!-- Page (\d+) -->
    page_parts = re.split(r"<!--\s*[Pp]age\s*(\d+)\s*-->", content)
    pages = []
    if len(page_parts) > 1:
        for i in range(1, len(page_parts), 2):
            p_num = int(page_parts[i])
            p_text = page_parts[i+1]
            # Skip preliminary Table of Contents (pages 1-13 in standard bare Acts)
            if p_num >= 14:
                pages.append((p_num, p_text))
    else:
        pages.append((1, content))

    full_body = ""
    page_map = []
    for p_num, p_text in pages:
        page_map.append((len(full_body), p_num))
        full_body += p_text + "\n"

    def get_page(char_idx):
        res = pages[0][0] if pages else 14
        for s_idx, p in page_map:
            if char_idx >= s_idx:
                res = p
            else:
                break
        return res

    # Find chapters
    chap_regex = re.compile(r"^[ \t]*(CHAPTER\s+[IVXLCDM\d]+[^\n]*\n+[A-Z\s,]+)", re.MULTILINE)
    chapters = []
    for m in chap_regex.finditer(full_body):
        chap_title = " ".join(m.group(1).split())
        chapters.append((m.start(), chap_title))

    def get_chapter(char_idx):
        res = "CHAPTER I PRELIMINARY"
        for s_idx, title in chapters:
            if char_idx >= s_idx:
                res = title
            else:
                break
        return res

    # Find sections: For Indian Acts, starts with number followed by full stop and heading
    sec_regex = re.compile(
        r"^[ \t]*(?:#{1,6}\s+)?(\d+[A-Z]?)\.\s+([A-Za-z][^\n.—]+?)(?:[.—]|\s*—)",
        re.MULTILINE
    )

    matches = list(sec_regex.finditer(full_body))
    valid_sections = []
    for m in matches:
        sec_num = m.group(1)
        sec_title = m.group(2).strip()
        # Filter out footnotes and false positives
        if any(sec_title.startswith(w) for w in [
            "Subs", "The words", "Ins", "Omitted", "vide", "Earlier", 
            "Added", "Provided", "Proviso", "Every", "Where", "Notwithstanding",
            "Nothing", "Any", "All", "In particular", "For the purposes",
            "Subject to", "A company", "An asset", "A managerial", "The number",
            "Sub-section", "Clause"
        ]):
            continue
        if "w.e.f." in sec_title or "omitted by" in sec_title.lower() or "notification" in sec_title.lower() or "substituted" in sec_title.lower():
            continue
        valid_sections.append({
            "start": m.start(),
            "end": m.end(),
            "sec_num": sec_num,
            "sec_title": sec_title,
        })

    chunks = []
    for i, sec in enumerate(valid_sections):
        start_pos = sec["start"]
        end_pos = valid_sections[i+1]["start"] if (i + 1 < len(valid_sections)) else len(full_body)
        sec_text = full_body[start_pos:end_pos].strip()
        
        page_num = get_page(start_pos)
        chapter = get_chapter(start_pos)

        # Split section if longer than 800 tokens with 100 overlap
        sub_chunks = split_tokens(sec_text, tokenizer, max_tokens=800, overlap=100)

        for part_idx, part_text in enumerate(sub_chunks, start=1):
            chunk_record = {
                "source_file": filename,
                "act_name": act_name,
                "year": year,
                "act_year": year,
                "is_current": True,
                "chapter": chapter,
                "section_number": sec["sec_num"],
                "section_title": sec["sec_title"],
                "page": page_num,
                "part": part_idx,
                "total_parts": len(sub_chunks),
                "text": part_text
            }
            chunks.append(chunk_record)

    return chunks

def main():
    parsed_dir = "parsed"
    parse_pdf_if_needed("companiesact2013.pdf", parsed_dir)

    md_files = glob.glob(os.path.join(parsed_dir, "*.md"))
    if not md_files:
        print(f"No markdown files found in {parsed_dir}")
        return

    tokenizer = get_tokenizer()
    all_chunks = []
    for md_file in md_files:
        print(f"Processing markdown file: {md_file}...")
        file_chunks = process_markdown_file(md_file, tokenizer)
        all_chunks.extend(file_chunks)

    output_file = "chunks.jsonl"
    with open(output_file, "w", encoding="utf-8") as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    print("\n" + "="*80)
    print(f"SUCCESS: Saved {len(all_chunks)} chunks to {output_file}")
    print("="*80)

    # Print three sample chunks with their metadata and total count
    print("\n--- SAMPLE CHUNKS (3 SAMPLES) ---")
    samples = []
    # Pick Sec 1, Sec 177, Sec 185
    sec_targets = ["1", "177", "185"]
    for target in sec_targets:
        match = next((c for c in all_chunks if c["section_number"] == target and c["part"] == 1), None)
        if match and match not in samples:
            samples.append(match)
    while len(samples) < 3 and len(samples) < len(all_chunks):
        for c in all_chunks:
            if c not in samples:
                samples.append(c)
                break

    for i, sample in enumerate(samples, start=1):
        print(f"\n[SAMPLE CHUNK {i}]")
        print(f"Source File   : {sample['source_file']}")
        print(f"Act Name      : {sample['act_name']}")
        print(f"Year          : {sample['year']}")
        print(f"Chapter       : {sample['chapter']}")
        print(f"Section Number: {sample['section_number']}")
        print(f"Section Title : {sample['section_title']}")
        print(f"Page          : {sample['page']}")
        print(f"Text Preview  : {sample['text'][:250]}...")

    print("\n" + "="*80)
    print(f"TOTAL CHUNKS COUNT: {len(all_chunks)}")
    print("="*80 + "\n")

if __name__ == "__main__":
    main()
