#!/usr/bin/env python3
"""
PPTX to PDF Converter (LibreOffice Headless)
Uses LibreOffice in headless mode to convert slides to PDF without Microsoft PowerPoint.
This is the best free, local method to preserve complex layouts (Quads/Charts).

Prerequisite: 
    Install LibreOffice: https://www.libreoffice.org/download/download/

Usage:
    python convert_to_pdf.py "input/*.pptx"
"""
import os
import sys
import glob
import argparse
import logging
import subprocess
import shutil
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
_log = logging.getLogger(__name__)

def find_libreoffice_binary():
    """
    Attempts to find the LibreOffice 'soffice' executable.
    Checks system PATH and standard Windows installation directories.
    """
    # 1. Check if 'soffice' is already in PATH
    if shutil.which("soffice"):
        return "soffice"
    
    # 2. Check standard Windows locations
    possible_paths = [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
            
    return None

def convert_pptx_to_pdf(input_path: str, output_dir: str, soffice_path: str):
    """
    Converts a single PPTX file to PDF using LibreOffice headless mode.
    """
    input_path = os.path.abspath(input_path)
    output_dir = os.path.abspath(output_dir)
    
    try:
        _log.info(f"Converting: {os.path.basename(input_path)}...")
        
        # Construct command: soffice --headless --convert-to pdf --outdir <dir> <file>
        cmd = [
            soffice_path,
            "--headless",
            "--convert-to", "pdf",
            "--outdir", output_dir,
            input_path
        ]
        
        # Run conversion
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            _log.info(f"✅ Success: {os.path.basename(input_path)} -> PDF")
        else:
            _log.error(f"❌ Conversion failed for {os.path.basename(input_path)}")
            _log.error(f"   Error: {result.stderr}")

    except Exception as e:
        _log.error(f"❌ Failed to convert {os.path.basename(input_path)}: {e}")

def main():
    parser = argparse.ArgumentParser(description="Batch convert PPTX to PDF using LibreOffice")
    parser.add_argument("input", help="Input file or glob pattern (e.g., 'folder/*.pptx')")
    args = parser.parse_args()

    # 1. Find LibreOffice
    soffice_path = find_libreoffice_binary()
    if not soffice_path:
        _log.error("❌ LibreOffice not found.")
        _log.error("   Please install it from https://www.libreoffice.org/")
        _log.error("   Or add 'soffice' to your System PATH.")
        sys.exit(1)
        
    _log.info(f"Using LibreOffice at: {soffice_path}")

    # 2. Find Files
    files = glob.glob(args.input)
    if not files:
        _log.warning(f"No files found matching: {args.input}")
        return

    # 3. Process Batch
    for file_path in files:
        path_obj = Path(file_path)
        
        # LibreOffice --outdir takes a DIRECTORY, not a full filename.
        # It automatically keeps the same filename but changes extension to .pdf
        output_dir = path_obj.parent
        
        convert_pptx_to_pdf(str(path_obj), str(output_dir), soffice_path)

if __name__ == "__main__":
    main()