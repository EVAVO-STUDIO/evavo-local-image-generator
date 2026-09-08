#!/usr/bin/env python3
"""
EVAVO Complete Startup & Monitoring System
Starts ComfyUI, waits for readiness, then runs autonomous generation
"""

import subprocess
import time
import requests
import os
import sys
import signal
from datetime import datetime
import json

class EVAVOStartupManager:
    def __init__(self):
        self.comfyui_url = "http://127.0.0.1:8188"
        self.comfyui_process = None
        self.start_time = datetime.now()
        self.max_startup_wait = 120  # seconds
        self.health_check_interval = 2  # seconds
        
    def log(self, level, message):
        """Structured logging"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        prefix = f"[{timestamp}] [{level:8s}]"
        print(f"{prefix} {message}")
        
    def banner(self, title):
        """Print section banner"""
        border = "=" * 70
        print(f"\n{border}")
        print(f"  {title}")
        print(f"{border}\n")
        
    def start_comfyui(self):
        """Start ComfyUI server"""
        self.banner("STARTING COMFYUI SERVER")
        
        comfyui_path = "C:\\AI\\ComfyUI"
        if not os.path.exists(comfyui_path):
            self.log("ERROR", f"ComfyUI not found at {comfyui_path}")
            return False
            
        try:
            self.log("INFO", f"Launching ComfyUI from {comfyui_path}")
            
            # Start ComfyUI in background
            self.comfyui_process = subprocess.Popen(
                ["python", "main.py"],
                cwd=comfyui_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
            )
            
            self.log("SUCCESS", f"ComfyUI process started (PID: {self.comfyui_process.pid})")
            return True
            
        except Exception as e:
            self.log("ERROR", f"Failed to start ComfyUI: {e}")
            return False
    
    def wait_for_readiness(self):
        """Wait for ComfyUI to be ready with exponential backoff"""
        self.banner("WAITING FOR COMFYUI READINESS")
        
        start = time.time()
        attempt = 0
        wait_time = 2
        
        while time.time() - start < self.max_startup_wait:
            attempt += 1
            
            try:
                response = requests.get(
                    f"{self.comfyui_url}/system_stats",
                    timeout=5
                )
                
                if response.status_code == 200:
                    stats = response.json()
                    self.log("SUCCESS", "✓ ComfyUI is ready!")
                    self.log("INFO", f"  GPU Memory: {stats.get('ram', {}).get('used', 'N/A')} MB")
                    return True
                    
            except requests.exceptions.ConnectionError:
                elapsed = time.time() - start
                self.log("INFO", f"  Attempt {attempt}: Waiting for ComfyUI ({elapsed:.1f}s)...")
                time.sleep(wait_time)
                wait_time = min(wait_time * 1.5, 10)  # Exponential backoff, max 10s
                
            except Exception as e:
                self.log("ERROR", f"  Health check error: {e}")
                time.sleep(wait_time)
        
        self.log("ERROR", "✗ ComfyUI failed to start within timeout")
        return False
    
    def check_models(self):
        """Verify required models are available"""
        self.banner("CHECKING MODELS")
        
        try:
            response = requests.get(f"{self.comfyui_url}/models", timeout=10)
            if response.status_code == 200:
                models = response.json()
                
                model_info = {
                    "checkpoints": len(models.get("checkpoints", [])),
                    "vae": len(models.get("vae", [])),
                    "loras": len(models.get("loras", [])),
                    "upscalers": len(models.get("upscale_models", []))
                }
                
                self.log("INFO", f"✓ Models loaded: {json.dumps(model_info, indent=2)}")
                return True
                
        except Exception as e:
            self.log("WARNING", f"Could not verify models: {e}")
            return True  # Don't fail if we can't check
    
    def run_generation(self):
        """Run autonomous generation"""
        self.banner("STARTING AUTONOMOUS GENERATION")
        
        try:
            repo_path = "C:\\Gitrepos\\evavo-local-image-generator"
            
            self.log("INFO", f"Launching autonomous generation from {repo_path}")
            
            result = subprocess.run(
                ["python", "run_autonomous.py"],
                cwd=repo_path,
                capture_output=False,
                text=True
            )
            
            return result.returncode == 0
            
        except Exception as e:
            self.log("ERROR", f"Failed to run generation: {e}")
            return False
    
    def shutdown(self, sig=None, frame=None):
        """Graceful shutdown"""
        self.banner("SHUTTING DOWN")
        
        if self.comfyui_process:
            self.log("INFO", "Terminating ComfyUI...")
            try:
                self.comfyui_process.terminate()
                self.comfyui_process.wait(timeout=10)
                self.log("SUCCESS", "ComfyUI terminated")
            except Exception as e:
                self.log("ERROR", f"Error terminating ComfyUI: {e}")
                self.comfyui_process.kill()
        
        elapsed = (datetime.now() - self.start_time).total_seconds()
        self.log("INFO", f"Total runtime: {elapsed:.1f} seconds")
        sys.exit(0)
    
    def run(self):
        """Main execution flow"""
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.shutdown)
        if sys.platform != "win32":
            signal.signal(signal.SIGTERM, self.shutdown)
        
        self.banner("EVAVO COMPLETE STARTUP & GENERATION SYSTEM")
        
        # Phase 1: Start ComfyUI
        if not self.start_comfyui():
            self.shutdown()
        
        time.sleep(3)  # Give process time to initialize
        
        # Phase 2: Wait for readiness
        if not self.wait_for_readiness():
            self.shutdown()
        
        time.sleep(2)
        
        # Phase 3: Check models
        self.check_models()
        
        # Phase 4: Run generation
        self.banner("GENERATION IN PROGRESS")
        if self.run_generation():
            self.log("SUCCESS", "✓ Generation completed successfully")
        else:
            self.log("ERROR", "✗ Generation encountered errors")
        
        self.shutdown()

if __name__ == "__main__":
    manager = EVAVOStartupManager()
    manager.run()
