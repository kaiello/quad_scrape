import os
import json

# CHANGE THIS IF YOUR MODEL IS SOMEWHERE ELSE
MODEL_DIR = r"C:\Qwen_Local"

index_path = os.path.join(MODEL_DIR, "model.safetensors.index.json")

print(f"Loading index: {index_path}")
with open(index_path, "r", encoding="utf-8") as f:
    index = json.load(f)

weight_map = index.get("weight_map", {})
fixed_weight_map = {}

for key, value in weight_map.items():
    # Take only the last path component (filename)
    filename = os.path.basename(value)

    # Fix bad extension if present
    if filename.endswith(".ssafetensors"):
        print(f"Fixing bad extension for {key}: {filename}")
        filename = filename.replace(".ssafetensors", ".safetensors")

    fixed_weight_map[key] = filename

index["weight_map"] = fixed_weight_map

# Optional: sanity check for missing files
missing = []
for filename in set(fixed_weight_map.values()):
    full_path = os.path.join(MODEL_DIR, filename)
    if not os.path.exists(full_path):
        missing.append(full_path)

if missing:
    print("\nWARNING: The following weight files are missing on disk:")
    for path in missing:
        print("  ", path)
    print("If you see paths here, your model download may be incomplete.")
else:
    print("All referenced weight shard files exist on disk.")

# Backup old index
backup_path = index_path + ".bak"
print(f"\nBacking up original index to: {backup_path}")
os.replace(index_path, backup_path)

# Write patched index
with open(index_path, "w", encoding="utf-8") as f:
    json.dump(index, f, indent=2)

print("\nPatched index written successfully.")
