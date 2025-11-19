from huggingface_hub import snapshot_download

# Define the model and where we want it (Hardcoded C:\Qwen_Local)
model_id = "Qwen/Qwen2-VL-2B-Instruct"
local_folder = r"C:/Qwen_Local"

print(f"🚀 Starting download of {model_id} to {local_folder}...")
print("This may take a few minutes (approx 4.5 GB)...")

try:
    snapshot_download(
        repo_id=model_id,
        local_dir=local_folder,
        local_dir_use_symlinks=False,  # Crucial for Windows to avoid "ghost" files
        resume_download=True
    )
    print(f"✅ Download Complete! Files are safely in {local_folder}")
except Exception as e:
    print(f"❌ Download failed: {e}")