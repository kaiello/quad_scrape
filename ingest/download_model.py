from huggingface_hub import snapshot_download
import os

# We will download specifically to this simple folder
# avoiding the deep .cache paths that are causing errors.
LOCAL_PATH = r"C:\nanonets_model"

def force_download():
    print(f"🚀 Starting Direct Download to: {LOCAL_PATH}")
    print("   This bypasses the cache system to prevent the 'directory' error.")
    
    try:
        snapshot_download(
            repo_id="nanonets/Nanonets-OCR2-3B",
            local_dir=LOCAL_PATH,
            local_dir_use_symlinks=False,  # CRITICAL: Forces real files, no links
            resume_download=True           # Smart resume if it drops
        )
        print(f"\n✅ SUCCESS! Model is ready at: {LOCAL_PATH}")
        print("   (You can now delete C:\\hf to save space if you want)")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    force_download()