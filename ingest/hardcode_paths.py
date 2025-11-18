import json
import os

# 1. Define your model folder
model_folder = r"C:\nanonets_model"
index_path = os.path.join(model_folder, "model.safetensors.index.json")

print(f"Checking index file at: {index_path}")

try:
    # 2. Load the index
    with open(index_path, "r") as f:
        data = json.load(f)

    # 3. Rewrite the "weight_map" to use FULL ABSOLUTE PATHS
    modified_count = 0
    new_map = {}
    
    for key, filename in data["weight_map"].items():
        # Strip any existing folder info just to be safe
        clean_filename = os.path.basename(filename)
        
        # Force create the absolute path: C:\nanonets_model\model-00001...
        abs_path = os.path.join(model_folder, clean_filename)
        
        new_map[key] = abs_path
        modified_count += 1

    data["weight_map"] = new_map

    # 4. Save the fixed index
    with open(index_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"✅ Success! Rewrote {modified_count} entries to use absolute paths.")
    print("The Transformers library will now be forced to find the files correctly.")

except Exception as e:
    print(f"❌ Error: {e}")