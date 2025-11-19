import os

MODEL_DIR = r"C:\Qwen_Local"

hits = []

for root, dirs, files in os.walk(MODEL_DIR):
    for name in files:
        if name.lower().endswith(".json"):
            path = os.path.join(root, name)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
            except Exception as e:
                print(f"Skipping {path} (read error: {e})")
                continue
            if ".ssafetensors" in text:
                hits.append(path)

if hits:
    print("Found '.ssafetensors' in the following JSON files:")
    for h in hits:
        print("  ", h)
else:
    print("No '.ssafetensors' strings found in any JSON under", MODEL_DIR)
