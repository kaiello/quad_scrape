import os
import json

MODEL_DIR = r"C:\Qwen_Local"  # change if your model lives elsewhere

def fix_string(value: str) -> str:
    """
    Normalize any path-like string to just the filename and fix .ssafetensors → .safetensors.
    """
    base = os.path.basename(value)

    # Fix bogus .ssafetensors extension
    if base.endswith(".ssafetensors"):
        print(f"  - Fixing bad extension in '{value}' -> '{base.replace('.ssafetensors', '.safetensors')}'")
        base = base.replace(".ssafetensors", ".safetensors")

    return base

def recursively_fix(obj):
    """
    Recursively walk the JSON structure and normalize *values* that are strings.
    """
    if isinstance(obj, dict):
        return {k: recursively_fix(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [recursively_fix(v) for v in obj]
    elif isinstance(obj, str):
        # Only touch safetensors-related paths
        if ".safetensors" in obj or ".ssafetensors" in obj:
            return fix_string(obj)
        return obj
    else:
        return obj

def patch_index_file(path: str):
    print(f"\n>>> Patching index file: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    data_fixed = recursively_fix(data)

    # Backup original
    backup_path = path + ".bak"
    if not os.path.exists(backup_path):
        print(f"  - Backing up original to: {backup_path}")
        os.replace(path, backup_path)
    else:
        print(f"  - Backup already exists: {backup_path}")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data_fixed, f, indent=2)

    # Sanity: warn if any '.ssafetensors' strings are still present
    with open(path, "r", encoding="utf-8") as f:
        txt = f.read()
    if ".ssafetensors" in txt:
        print("  ⚠️ WARNING: '.ssafetensors' still present in file after patch.")
    else:
        print("  ✅ No '.ssafetensors' strings remain in this index.")

def main():
    print(f"Scanning for *.index.json under: {MODEL_DIR}")
    for root, dirs, files in os.walk(MODEL_DIR):
        for name in files:
            if name.endswith(".index.json"):
                full_path = os.path.join(root, name)
                patch_index_file(full_path)

    print("\nDone patching all index files.")

if __name__ == "__main__":
    main()
