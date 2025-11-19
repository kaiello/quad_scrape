#!/usr/bin/env python3
"""
Environment Health Check for Docling + Unstructured Pipeline
"""
import shutil
import sys
import importlib.util

def check_package(package_name, import_name=None):
    """Checks if a Python package is installed and importable."""
    if import_name is None:
        import_name = package_name
    
    if importlib.util.find_spec(import_name) is None:
        print(f"❌ MISSING Python Package: '{package_name}'")
        return False
    else:
        try:
            # Try an actual import to catch runtime errors
            __import__(import_name)
            print(f"✅ INSTALLED Python Package: '{package_name}'")
            return True
        except ImportError as e:
            print(f"⚠️  ERROR Importing '{package_name}': {e}")
            return False

def check_system_binary(binary_name):
    """Checks if a system binary (like Tesseract) is in the PATH."""
    path = shutil.which(binary_name)
    if path:
        print(f"✅ FOUND System Binary: '{binary_name}' at {path}")
        return True
    else:
        print(f"❌ MISSING System Binary: '{binary_name}'")
        return False

def main():
    print("--- 🔍 Starting Environment Check ---\n")
    
    all_good = True

    # 1. Check Python Dependencies
    print("[Python Libraries]")
    # Check Docling
    if not check_package("docling"):
        all_good = False
    # Check Unstructured (we only need the base package for the schema)
    if not check_package("unstructured"):
        all_good = False
    
    print("-" * 30)

    # 2. Check System Dependencies (OCR)
    print("[System Dependencies]")
    if not check_system_binary("tesseract"):
        print("   -> REQUIRED for OCR options (scanned docs).")
        print("   -> Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki")
        print("   -> Mac: 'brew install tesseract'")
        print("   -> Linux: 'sudo apt-get install tesseract-ocr'")
        all_good = False

    print("\n" + "-" * 30)
    
    # 3. Summary
    if all_good:
        print("🚀 SUCCESS: Your environment is ready to run the script.")
    else:
        print("🛑 FAILURE: Please install the missing components above.")
        sys.exit(1)

if __name__ == "__main__":
    main()