import os, json, glob, pathlib, re

IN_DIR, OUT_DIR = r"tmp_norm", r"tmp_chunks"
MAX_CHARS, OVERLAP = 1200, 200

os.makedirs(OUT_DIR, exist_ok=True)

# Keys that are likely to contain text
TEXTY_KEYS = {"text","content","body","paragraph","paragraphs","page_text","ocr","document","doc","value"}

# Skip obviously non-text payloads by extension/pattern
BINLIKE_PAT = re.compile(r'^\s*%PDF-|^[A-Za-z0-9+/=\s]{200,}$')  # pdf header or long base64-ish blobs

def is_texty_key(k: str) -> bool:
    k = (k or "").lower()
    return any(t in k for t in TEXTY_KEYS)

def collect_strings(x, out):
    """Deep-collect strings from any nested structure, preferring keys that look texty."""
    if isinstance(x, str):
        if not BINLIKE_PAT.search(x):
            out.append(x)
        return
    if isinstance(x, dict):
        # First pass: texty keys
        for k,v in x.items():
            if is_texty_key(k):
                collect_strings(v, out)
        # Second pass: everything else (so we don't miss text nested elsewhere)
        for k,v in x.items():
            if not is_texty_key(k):
                collect_strings(v, out)
    elif isinstance(x, list):
        for v in x:
            collect_strings(v, out)

def chunk_text(s, max_chars=MAX_CHARS, overlap=OVERLAP):
    s = s or ""
    if not s.strip():
        return []
    chunks, i, n = [], 0, len(s)
    step = max(max_chars - overlap, 1)
    while i < n:
        chunks.append(s[i:i+max_chars])
        i += step
    return chunks

written = 0
for f in glob.glob(os.path.join(IN_DIR, "*.normalized.json")):
    with open(f, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    strings = []
    collect_strings(data, strings)
    # Deduplicate small repeated snippets; keep order
    seen = set()
    deduped = []
    for s in strings:
        key = s.strip()
        if key and key not in seen:
            seen.add(key)
            deduped.append(key)

    text = "\n".join(deduped)
    chunks = chunk_text(text)
    if not chunks:
        continue

    out_path = os.path.join(OUT_DIR, pathlib.Path(f).name + "l")  # *.normalized.jsonl
    with open(out_path, "w", encoding="utf-8") as out:
        for idx, ch in enumerate(chunks):
            rec = {"doc_id": os.path.basename(f), "chunk_id": idx, "text": ch}
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            written += 1

print(f"wrote_chunks={written} to {OUT_DIR}")
