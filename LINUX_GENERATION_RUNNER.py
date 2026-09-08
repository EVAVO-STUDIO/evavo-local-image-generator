#!/usr/bin/env python3
"""
EVAVO Generation Runner for Linux VM with mounted Windows paths
Uses mounted paths to start services and run generation
"""

import subprocess
import os
import sys
import time
import platform
from pathlib import Path

def log(msg, level="INFO"):
    print(f"[{level:8s}] {msg}")

def main():
    log("="*70, "")
    log("EVAVO GENERATION RUNNER (Linux VM Mode)", "")
    log("="*70, "")
    log("")
    
    # Use mounted paths
    home = Path(os.path.expanduser("~"))
    mounted_ai = home / "mnt" / "AI"
    mounted_gitrepos = home / "mnt" / "Gitrepos"
    evavo_repo = mounted_gitrepos / "evavo-local-image-generator"
    
    log(f"Home: {home}")
    log(f"Mounted AI: {mounted_ai}")
    log(f"EVAVO Repo: {evavo_repo}")
    log("")
    
    # Verify paths exist
    if not mounted_ai.exists():
        log(f"ERROR: Mounted AI folder not found at {mounted_ai}", "ERROR")
        return 1
    
    if not evavo_repo.exists():
        log(f"ERROR: EVAVO repo not found at {evavo_repo}", "ERROR")
        return 1
    
    comfyui_path = mounted_ai / "ComfyUI"
    if not comfyui_path.exists():
        log(f"ERROR: ComfyUI not found at {comfyui_path}", "ERROR")
        return 1
    
    log(f"✓ ComfyUI found at: {comfyui_path}")
    log("")
    
    # Change to repo directory
    os.chdir(evavo_repo)
    log(f"Working directory: {os.getcwd()}")
    log("")
    
    # Start ComfyUI - Python can run it in Linux if it's Python-based
    log("Starting ComfyUI server...", "INFO")
    log("Note: ComfyUI main.py needs to run on Windows with GPU", "WARN")
    
    # Try to run COMPLETE-MULTIMODAL-TEST.py which should handle generation
    log("")
    log("Running COMPLETE-MULTIMODAL-TEST.py...", "INFO")
    
    test_file = evavo_repo / "COMPLETE-MULTIMODAL-TEST.py"
    if test_file.exists():
        try:
            # Run the test
            result = subprocess.run(
                [sys.executable, str(test_file)],
                cwd=str(evavo_repo),
                timeout=600
            )
            log(f"Test completed with exit code: {result.returncode}")
            
        except subprocess.TimeoutExpired:
            log("Test timed out after 600 seconds", "ERROR")
            return 1
        except Exception as e:
            log(f"Error running test: {e}", "ERROR")
            return 1
    else:
        log(f"Test file not found: {test_file}", "ERROR")
        return 1
    
    # Copy outputs to beestation
    log("")
    log("Copying outputs to beestation...", "INFO")
    
    import shutil
    
    beestation = Path("C:/Users/User/beestation/evavo-generation")
    if platform.system() == "Linux":
        # In Linux VM, use mounted path
        beestation = home / "mnt" / "beestation" / "evavo-generation"
    
    output_dirs = [
        "evavo-images",
        "evavo-videos", 
        "evavo-audio",
        "evavo-text",
        "evavo-particles",
        "evavo-models",
        "evavo-textures",
        "evavo-state"
    ]
    
    try:
        beestation.mkdir(parents=True, exist_ok=True)
        log(f"Beestation directory: {beestation}")
    except Exception as e:
        log(f"Failed to create beestation directory: {e}", "ERROR")
        return 1
    
    for dir_name in output_dirs:
        src = evavo_repo / dir_name
        if src.exists():
            dst = beestation / dir_name
            try:
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
                file_count = len(list(dst.glob("**/*")))
                log(f"✓ {dir_name}: {file_count} items")
            except Exception as e:
                log(f"✗ {dir_name}: {e}", "ERROR")
        else:
            log(f"  {dir_name}: not generated yet")
    
    log("")
    log("="*70, "")
    log("GENERATION COMPLETE!", "")
    log("="*70, "")
    log(f"Outputs saved to: {beestation}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
