#!/usr/bin/env python3
"""
EVAVO Automated Generation Runner
Executes the full generation pipeline including service startup
"""

import subprocess
import sys
import os
import time
from pathlib import Path

def main():
    print("="*70)
    print("EVAVO AUTOMATED GENERATION SYSTEM")
    print("="*70)
    print()
    
    # Change to script directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    print(f"Working directory: {os.getcwd()}")
    print()
    
    # Start ComfyUI
    print("1. Starting ComfyUI server...")
    try:
        comfyui_proc = subprocess.Popen(
            [sys.executable, "main.py"],
            cwd="C:\\AI\\ComfyUI",
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        print(f"   ✓ ComfyUI started (PID: {comfyui_proc.pid})")
    except FileNotFoundError:
        print(f"   ✗ ComfyUI not found at C:\\AI\\ComfyUI")
    except Exception as e:
        print(f"   ✗ Error starting ComfyUI: {e}")
    
    time.sleep(3)
    
    # Start Ollama
    print("2. Starting Ollama server...")
    try:
        ollama_proc = subprocess.Popen(
            "ollama serve",
            shell=True,
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        print(f"   ✓ Ollama started (PID: {ollama_proc.pid})")
    except Exception as e:
        print(f"   ✗ Error starting Ollama: {e}")
    
    time.sleep(3)
    
    # Run generation
    print("3. Running EVAVO multi-modal generation test...")
    try:
        result = subprocess.run(
            [sys.executable, "COMPLETE-MULTIMODAL-TEST.py"],
            timeout=600
        )
        print(f"   ✓ Generation completed (exit code: {result.returncode})")
    except subprocess.TimeoutExpired:
        print(f"   ✗ Generation timed out after 600 seconds")
    except Exception as e:
        print(f"   ✗ Error running generation: {e}")
    
    # Copy outputs
    print()
    print("4. Copying outputs to beestation...")
    
    import shutil
    
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
    
    beestation_path = Path("C:\\Users\\User\\beestation\\evavo-generation")
    beestation_path.mkdir(parents=True, exist_ok=True)
    
    for dir_name in output_dirs:
        src = Path(dir_name)
        if src.exists():
            dst = beestation_path / dir_name
            try:
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
                print(f"   ✓ {dir_name}")
            except Exception as e:
                print(f"   ✗ {dir_name}: {e}")
    
    print()
    print("="*70)
    print("GENERATION COMPLETE!")
    print("="*70)
    print()
    print(f"All outputs saved to: C:\\Users\\User\\beestation\\evavo-generation\\")
    print()
    print("Generated directories:")
    for dir_name in output_dirs:
        dst = beestation_path / dir_name
        if dst.exists():
            file_count = len(list(dst.glob("*")))
            print(f"  ✓ {dir_name}: {file_count} files")
    print()

if __name__ == "__main__":
    main()
