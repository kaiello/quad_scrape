import os, json, glob, pprint

IN_DIR = r"tmp_norm"

def summarize(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    top = list(data.keys()) if isinstance(data, dict) else type(data).__name__
    print(f"\n=== {os.path.basename(path)} ===")
    print("top-level keys:", top if isinstance(top, list) else top)

    # Heuristic peeks
    def find_paths(d, prefix="$", hits=None):
        if hits is None: hits=[]
        if isinstance(d, dict):
            for k,v in d.items():
                p = f"{prefix}.{k}"
                if isinstance(v, str) and v.strip():
                    if any(tag in k.lower() for tag in ("text","content","body","paragraph","doc","ocr")):
                        hits.append((p, min(len(v), 80)))
                elif isinstance(v, (list,dict)):
                    find_paths(v, p, hits)
        elif isinstance(d, list):
            for i,v in enumerate(d[:5]):  # peek first few
                p = f"{prefix}[{i}]"
                if isinstance(v, str) and v.strip():
                    hits.append((p, min(len(v), 80)))
                elif isinstance(v, (list,dict)):
                    find_paths(v, p, hits)
        return hits

    hits = find_paths(data)
    if hits:
        print("candidate text paths (sampled):")
        for p,_ in hits[:10]:
            print("  ", p)
    else:
        print("no obvious text paths found (will try deep scan later)")

files = glob.glob(os.path.join(IN_DIR, "*.normalized.json"))
for f in files:
    summarize(f)
