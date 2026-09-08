#!/usr/bin/env python3
"""Start ComfyUI and generate images autonomously"""

import subprocess
import time
import logging
import sys
import os
import platform

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - STARTUP - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Use mounted path in Linux VM
if platform.system() == "Linux":
    COMFYUI_PATH = os.path.expanduser("~/mnt/AI/ComfyUI")
else:
    COMFYUI_PATH = r"C:\AI\ComfyUI"

COMFYUI_URL = "http://127.0.0.1:8188"
MAX_STARTUP_WAIT = 120
HEALTH_CHECK_INTERVAL = 2

def start_comfyui():
    """Start ComfyUI server in background"""
    logger.info("=" * 70)
    logger.info("STARTING COMFYUI SERVER")
    logger.info("=" * 70)
    logger.info(f"Platform: {platform.system()}")
    logger.info(f"ComfyUI path: {COMFYUI_PATH}")
    
    if not os.path.exists(COMFYUI_PATH):
        logger.error(f"ComfyUI path not found: {COMFYUI_PATH}")
        return None
    
    try:
        logger.info("Launching ComfyUI...")
        
        # Use different subprocess flags for different platforms
        kwargs = {
            'cwd': COMFYUI_PATH,
            'stdout': subprocess.DEVNULL,
            'stderr': subprocess.DEVNULL,
        }
        
        if platform.system() == 'Windows':
            kwargs['creationflags'] = 0x00000008  # CREATE_NO_WINDOW
        
        process = subprocess.Popen(
            [sys.executable, "main.py"],
            **kwargs
        )
        
        logger.info(f"ComfyUI process started (PID: {process.pid})")
        return process
        
    except Exception as e:
        logger.error(f"Failed to start ComfyUI: {e}")
        return None

def wait_for_comfyui():
    """Wait for ComfyUI to be ready"""
    logger.info("Waiting for ComfyUI to be ready...")
    
    try:
        import requests
    except ImportError:
        logger.warning("requests not available, skipping health check")
        time.sleep(10)
        return True
    
    start_time = time.time()
    
    while time.time() - start_time < MAX_STARTUP_WAIT:
        try:
            response = requests.get(f"{COMFYUI_URL}/system_stats", timeout=5)
            if response.status_code == 200:
                logger.info("✓ ComfyUI is ready!")
                return True
        except:
            pass
        
        elapsed = int(time.time() - start_time)
        logger.info(f"  Still waiting... ({elapsed}s)")
        time.sleep(HEALTH_CHECK_INTERVAL)
    
    logger.error("ComfyUI did not respond within timeout")
    return False

def run_generation():
    """Run the autonomous generation pipeline"""
    logger.info("=" * 70)
    logger.info("STARTING AUTONOMOUS GENERATION")
    logger.info("=" * 70)
    
    try:
        result = subprocess.run(
            [sys.executable, "run_autonomous.py"],
            cwd=os.getcwd(),
            capture_output=False,
            text=True
        )
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Generation failed: {e}")
        return False

if __name__ == "__main__":
    logger.info(f"Running on platform: {platform.system()}")
    
    # Start ComfyUI
    comfyui_process = start_comfyui()
    
    if not comfyui_process:
        logger.error("Could not start ComfyUI")
        sys.exit(1)
    
    # Wait for it to be ready
    time.sleep(3)  # Initial delay
    if not wait_for_comfyui():
        logger.error("ComfyUI startup timed out")
        comfyui_process.terminate()
        sys.exit(1)
    
    # Run generation
    success = run_generation()
    
    logger.info("=" * 70)
    if success:
        logger.info("✓ GENERATION COMPLETE")
    else:
        logger.info("✗ GENERATION FAILED")
    logger.info("=" * 70)
    
    # Keep ComfyUI running for a bit
    time.sleep(5)
    
    sys.exit(0 if success else 1)
