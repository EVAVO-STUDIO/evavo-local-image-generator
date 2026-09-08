#!/usr/bin/env python3
"""
EVAVO Full Generation Pipeline Runner
Starts services and executes complete multi-modal generation
"""

import subprocess
import time
import requests
import json
import shutil
import sys
from pathlib import Path
from datetime import datetime

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")

def wait_for_service(url, timeout=120, service_name="Service"):
    """Wait for a service to be ready"""
    log(f"Waiting for {service_name} at {url}...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code < 500:
                log(f"✓ {service_name} is ready!")
                return True
        except:
            pass
        time.sleep(2)
    
    log(f"✗ {service_name} failed to start within {timeout}s")
    return False

def main():
    log("="*70)
    log("EVAVO FULL GENERATION PIPELINE")
    log("="*70)
    
    # Paths
    base_dir = Path.cwd()
    ai_dir = Path("$HOME/mnt/AI")
    beestation_dir = Path("$HOME/mnt/beestation")
    
    # Create output directory in beestation
    output_dir = beestation_dir / "evavo-generation"
    output_dir.mkdir(parents=True, exist_ok=True)
    log(f"Output directory: {output_dir}")
    
    # Start ComfyUI
    log("\n1. Starting ComfyUI server...")
    try:
        comfyui_proc = subprocess.Popen(
            [sys.executable, "main.py"],
            cwd=ai_dir / "ComfyUI",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        time.sleep(3)  # Initial startup time
        
        if wait_for_service("http://localhost:8188/system_stats", timeout=60, service_name="ComfyUI"):
            log("ComfyUI started successfully")
        else:
            log("ComfyUI startup warning - continuing anyway")
    except Exception as e:
        log(f"Note: ComfyUI not available ({e})")
    
    # Start Ollama
    log("\n2. Starting Ollama server...")
    try:
        ollama_proc = subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        time.sleep(3)  # Initial startup time
        
        if wait_for_service("http://localhost:11434/api/tags", timeout=60, service_name="Ollama"):
            log("Ollama started successfully")
        else:
            log("Ollama startup warning - continuing anyway")
    except Exception as e:
        log(f"Note: Ollama not available ({e})")
    
    # Run generation
    log("\n3. Running EVAVO multi-modal generation...")
    try:
        result = subprocess.run(
            [sys.executable, "COMPLETE-MULTIMODAL-TEST.py"],
            cwd=base_dir,
            timeout=600
        )
        log(f"Generation completed with code: {result.returncode}")
    except subprocess.TimeoutExpired:
        log("Generation timeout - may have completed anyway")
    except Exception as e:
        log(f"Generation error: {e}")
    
    # Copy outputs to beestation
    log("\n4. Copying outputs to beestation...")
    
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
    
    for dir_name in output_dirs:
        src = base_dir / dir_name
        if src.exists():
            dst = output_dir / dir_name
            try:
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
                log(f"  ✓ Copied {dir_name}")
            except Exception as e:
                log(f"  ✗ Error copying {dir_name}: {e}")
    
    # Summary
    log("\n" + "="*70)
    log("GENERATION COMPLETE")
    log("="*70)
    log(f"Outputs saved to: {output_dir}")
    
    # List generated files
    log("\nGenerated files:")
    for subdir in output_dir.glob("*"):
        if subdir.is_dir():
            files = list(subdir.glob("*"))
            log(f"  {subdir.name}: {len(files)} files")
    
    log("\n✓ All systems complete!")

if __name__ == "__main__":
    main()
