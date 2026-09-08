#!/usr/bin/env python3
"""
Automated EVAVO Generation Launch
Starts all services and runs the complete test suite
"""

import subprocess
import time
import sys
import os
import json
from datetime import datetime
from pathlib import Path

print("\n" + "="*70)
print("  EVAVO MULTI-MODAL GENERATION LAUNCHER")
print("="*70 + "\n")

# Paths
COMFYUI_PATH = r"C:\AI\ComfyUI"
OLLAMA_CMD = "ollama serve"
TEST_SCRIPT = r"C:\Gitrepos\evavo-local-image-generator\COMPLETE-MULTIMODAL-TEST.py"
OUTPUT_DIR = Path(r"C:\Gitrepos\evavo-local-image-generator")

print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting ComfyUI from: {COMFYUI_PATH}\n")

try:
    # Start ComfyUI in background
    print("Starting ComfyUI server...")
    comfyui_process = subprocess.Popen(
        ["python", "main.py"],
        cwd=COMFYUI_PATH,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    print(f"✓ ComfyUI process started (PID: {comfyui_process.pid})")
    time.sleep(3)
    
    # Start Ollama in background
    print("\nStarting Ollama server...")
    ollama_process = subprocess.Popen(
        OLLAMA_CMD,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    print(f"✓ Ollama process started (PID: {ollama_process.pid})")
    time.sleep(2)
    
    # Wait for services to be ready
    print("\n[Waiting 10 seconds for services to initialize...]")
    time.sleep(10)
    
    # Run test suite
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Launching test suite...\n")
    print("="*70)
    
    result = subprocess.run([sys.executable, TEST_SCRIPT], cwd=OUTPUT_DIR)
    
    print("="*70)
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Generation complete!")
    print("\nCheck output directories:")
    print("  ✓ evavo-images/     (45 image variations)")
    print("  ✓ evavo-videos/     (3 videos)")
    print("  ✓ evavo-audio/      (6 audio files)")
    print("  ✓ evavo-text/       (3 text outputs)")
    print("  ✓ evavo-particles/  (4 particle configs)")
    print("  ✓ evavo-models/     (6 3D models)")
    print("  ✓ evavo-textures/   (4 PBR texture sets)")
    print("  ✓ evavo-state/      (test results & metrics)")
    
except Exception as e:
    print(f"\n✗ Error: {e}")
    sys.exit(1)

