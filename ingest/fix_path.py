import json
import os

# Point this to your model folder
model_path = r"C:\nanonets_model"
index_file = os.path.join(model_path, "model.safetensors.index.json")

try:
    with open(index_file, 'r') as f:
        data = json.load(f)
    
    print("🔍 Checking index file...")
    modified = False
    
    # Check the weight_map
    if "weight_map" in data:
        new_map = {}
        for key, filename in data["weight_map"].items():
            # If the filename has a folder prefix (e.g. "nanonets/model-01..."), strip it
            base_name = os.path.basename(filename)
            if base_name != filename:
                modified = True
            new_map[key] = base_name
        
        data["weight_map"] = new_map

    if modified:
        print("⚠️ Found directory prefixes in the index file. Removing them...")
        with open(index_file, 'w') as f:
            json.dump(data, f, indent=2)
        print("✅ Index file fixed! You can now run your main script.")
    else:
        print("✅ Index file was already clean. The issue might be the Windows path style.")

except Exception as e:
    print(f"❌ Error: {e}")