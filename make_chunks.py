import os, json, glob, pathlib
IN_DIR, OUT_DIR = r"tmp_norm", r"tmp_chunks"
MAX_CHARS, OVERLAP = 1200, 200

os.makedirs(OUT_DIR, exist_ok=True)
def chunk(s, m=MAX_CHARS, ov=OVERLAP):
    s = s or ""; out=[]; i=0; n=len(s); step=max(m-ov,1)
    while i<n: out.append(s[i:i+m]); i+=step
    return out

written=0
for f in glob.glob(os.path.join(IN_DIR,"*.normalized.json")):
    data=json.load(open(f,encoding="utf-8"))
    text=data.get("text") or data.get("content") or ""
    if not text.strip():
        pages=data.get("pages") or data.get("blocks") or []
        if pages and isinstance(pages,list):
            text="\n".join([p.get("text","") if isinstance(p,dict) else str(p) for p in pages])
    chunks=chunk(text)
    if not chunks: continue
    out= os.path.join(OUT_DIR, pathlib.Path(f).name + "l")   # *.normalized.jsonl
    with open(out,"w",encoding="utf-8") as fo:
        for i,ch in enumerate(chunks):
            fo.write(json.dumps({"doc_id":os.path.basename(f),"chunk_id":i,"text":ch},ensure_ascii=False)+"\n")
            written+=1
print(f"wrote_chunks={written} to {OUT_DIR}")
