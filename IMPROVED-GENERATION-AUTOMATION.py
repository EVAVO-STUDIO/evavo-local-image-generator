#!/usr/bin/env python3
"""
IMPROVED GENERATION TEST AUTOMATION
Starts ComfyUI with GPU support and runs enhanced generation tests with better parameters.
"""
import subprocess
import sys
import os
import time
import requests
import json
from pathlib import Path

def run_command(cmd, shell=True, cwd=None):
    """Run a command and return success status."""
    try:
        result = subprocess.run(
            cmd,
            shell=shell,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300
        )
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def start_comfyui_server():
    """Start ComfyUI server with GPU support."""
    print("\n" + "="*70)
    print("STARTING COMFYUI SERVER WITH GPU SUPPORT")
    print("="*70)
    
    comfyui_dir = Path("C:\\AI\\ComfyUI")
    
    # First verify CUDA is available
    print("\n[1/3] Verifying CUDA availability...")
    success, stdout, stderr = run_command(
        'python -c "import torch; print(f\'CUDA Available: {torch.cuda.is_available()}\')"',
        cwd=str(comfyui_dir)
    )
    
    if success:
        print(f"  ✓ {stdout.strip()}")
    else:
        print(f"  ⚠ Could not verify CUDA: {stderr}")
    
    # Kill any existing Python processes (careful with this!)
    print("\n[2/3] Cleaning up old processes...")
    run_command("taskkill /F /IM python.exe /FI \"WINDOWTITLE eq ComfyUI*\" 2>nul", cwd=str(comfyui_dir))
    print("  ✓ Cleanup complete")
    
    # Start ComfyUI server
    print("\n[3/3] Starting ComfyUI server (this window will open separately)...")
    
    batch_content = """@echo off
cd /d C:\\AI\\ComfyUI
python main.py
"""
    
    batch_file = Path("C:\\AI\\start-comfyui.bat")
    batch_file.write_text(batch_content)
    
    # Use subprocess.Popen with CREATE_NEW_CONSOLE to spawn in new window
    try:
        subprocess.Popen(
            ["cmd.exe", "/c", str(batch_file)],
            cwd=str(comfyui_dir),
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
        )
        print("  ✓ Server process started")
        return True
    except Exception as e:
        print(f"  ✗ Failed to start server: {e}")
        return False

def wait_for_server_ready(max_attempts=90, interval=2):
    """Wait for ComfyUI server to be ready."""
    print("\n" + "="*70)
    print("WAITING FOR SERVER INITIALIZATION")
    print("="*70)
    print("Waiting for ComfyUI to initialize... (this may take up to 3 minutes)")
    
    for attempt in range(max_attempts):
        try:
            response = requests.get("http://127.0.0.1:8188/system_stats", timeout=5)
            if response.status_code == 200:
                print(f"\n✓ Server is ready! (after {attempt * interval} seconds)")
                return True
        except:
            pass
        
        print(".", end="", flush=True)
        time.sleep(interval)
    
    print(f"\n✗ Server did not respond after {max_attempts * interval} seconds")
    return False

def run_improved_generation_tests():
    """Run the improved generation test script."""
    print("\n" + "="*70)
    print("RUNNING IMPROVED GENERATION TESTS")
    print("="*70)
    print("\nExecuting test script with enhanced parameters...")
    print("  - Steps per generation: 25-30 (improved from 5)")
    print("  - Resolution: 768x768 (improved from 512x512)")
    print("  - Model: Stable Diffusion XL Base 1.0")
    print("  - Sampler: Euler with Karras scheduler")
    print("\nThis will take approximately 5-10 minutes per image...\n")
    
    test_script = Path("C:\\AI\\improved-generation-test.py")
    
    if not test_script.exists():
        print(f"✗ Test script not found: {test_script}")
        return False
    
    success, stdout, stderr = run_command(
        f"python {str(test_script)}",
        cwd="C:\\AI"
    )
    
    if success:
        print("\n✓ Generation tests completed successfully!")
        if stdout:
            print("\nTest output:")
            print(stdout)
        return True
    else:
        print(f"\n✗ Test execution failed")
        if stderr:
            print(f"Error output:\n{stderr}")
        return False

def collect_generated_images():
    """Collect and verify generated images."""
    print("\n" + "="*70)
    print("COLLECTING AND VERIFYING GENERATED IMAGES")
    print("="*70)
    
    output_dir = Path("C:\\AI\\ComfyUI\\output")
    
    if not output_dir.exists():
        print(f"✗ Output directory not found: {output_dir}")
        return []
    
    print(f"\nLooking for generated images in: {output_dir}")
    
    images = list(output_dir.glob("**/*.png"))
    
    if not images:
        print("✗ No images found!")
        return []
    
    print(f"✓ Found {len(images)} images:\n")
    
    results = []
    for img_path in sorted(images):
        size_mb = img_path.stat().st_size / (1024*1024)
        results.append({
            "path": str(img_path),
            "name": img_path.name,
            "size_mb": round(size_mb, 2)
        })
        print(f"  • {img_path.name} ({size_mb:.2f} MB)")
    
    # Save manifest
    manifest_file = Path("C:\\AI\\generation_tests\\image_manifest.json")
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    manifest_file.write_text(json.dumps(results, indent=2))
    print(f"\n✓ Image manifest saved to: {manifest_file}")
    
    return results

def main():
    """Main automation workflow."""
    print("\n")
    print("╔" + "="*68 + "╗")
    print("║" + " "*68 + "║")
    print("║" + "  EVAVO IMPROVED GENERATION TEST - FULL AUTOMATION".center(68) + "║")
    print("║" + " "*68 + "║")
    print("╚" + "="*68 + "╝")
    
    # Step 1: Start server
    if not start_comfyui_server():
        print("\n✗ Failed to start ComfyUI server")
        return False
    
    # Step 2: Wait for ready
    if not wait_for_server_ready():
        print("\n✗ Server failed to initialize")
        print("\nPlease check:")
        print("  1. Is ComfyUI installed in C:\\AI\\ComfyUI?")
        print("  2. Is Python 3.10+ installed?")
        print("  3. Are all dependencies installed (torch, comfy, etc)?")
        return False
    
    # Step 3: Run tests
    if not run_improved_generation_tests():
        print("\n✗ Generation tests failed")
        return False
    
    # Step 4: Collect results
    images = collect_generated_images()
    
    if images:
        print("\n" + "="*70)
        print("SUMMARY")
        print("="*70)
        print(f"✓ Successfully generated {len(images)} images")
        print(f"✓ All images saved to: C:\\AI\\ComfyUI\\output")
        print(f"✓ Manifest saved to: C:\\AI\\generation_tests\\image_manifest.json")
        return True
    else:
        print("\n✗ No images were generated")
        return False

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n✗ Automation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
