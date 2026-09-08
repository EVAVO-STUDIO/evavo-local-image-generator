#!/usr/bin/env python3
"""
EVAVO Fully Automated Generation System
Run this from Claude to execute complete multi-modal generation pipeline
Works on both Windows (direct) and Linux VM (mounted paths)

Usage:
    python EVAVO-AUTOMATION.py [--mode full|test|generate]
    
Modes:
    full      - Start services, run tests, copy outputs (default)
    test      - Run tests only (services must be running)
    generate  - Generate without tests
"""

import subprocess
import sys
import os
import time
import platform
import argparse
import json
from pathlib import Path
from datetime import datetime

class EVAVOAutomation:
    def __init__(self):
        self.platform = platform.system()
        self.is_linux = self.platform == "Linux"
        self.start_time = datetime.now()
        self.home = Path(os.path.expanduser("~"))
        
        # Set paths based on platform
        if self.is_linux:
            self.ai_path = self.home / "mnt" / "AI"
            self.repo_path = self.home / "mnt" / "Gitrepos" / "evavo-local-image-generator"
            self.beestation = self.home / "mnt" / "beestation" / "evavo-generation"
        else:
            self.ai_path = Path("C:\\AI")
            self.repo_path = Path("C:\\Gitrepos\\evavo-local-image-generator")
            self.beestation = Path("C:\\Users\\User\\beestation\\evavo-generation")
        
        self.comfyui_path = self.ai_path / "ComfyUI"
        self.kokoro_path = self.ai_path / "Kokoro-FastAPI"
        self.comfyui_url = "http://127.0.0.1:8188"
        
        self.processes = []
        
    def log(self, msg, level="INFO"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level:8s}] {msg}")
    
    def banner(self, title):
        border = "=" * 80
        print(f"\n{border}")
        print(f"  {title}")
        print(f"{border}\n")
    
    def verify_paths(self):
        """Verify all required paths exist"""
        self.banner("VERIFYING PATHS")
        
        paths_to_check = {
            "AI Folder": self.ai_path,
            "ComfyUI": self.comfyui_path,
            "EVAVO Repo": self.repo_path,
        }
        
        all_exist = True
        for name, path in paths_to_check.items():
            if path.exists():
                self.log(f"✓ {name}: {path}")
            else:
                self.log(f"✗ {name} NOT FOUND: {path}", "ERROR")
                all_exist = False
        
        if not all_exist:
            self.log("Some required paths are missing!", "ERROR")
            return False
        
        return True
    
    def start_comfyui(self):
        """Start ComfyUI server"""
        if self.is_linux:
            self.log("Running in Linux VM - ComfyUI cannot start here", "WARN")
            self.log("ComfyUI must be running on Windows before starting generation", "WARN")
            return True
        
        self.banner("STARTING COMFYUI SERVER")
        
        if not self.comfyui_path.exists():
            self.log(f"ComfyUI not found at {self.comfyui_path}", "ERROR")
            return False
        
        try:
            self.log(f"Launching ComfyUI from {self.comfyui_path}")
            
            proc = subprocess.Popen(
                [sys.executable, "main.py"],
                cwd=str(self.comfyui_path),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
            )
            
            self.processes.append(proc)
            self.log(f"✓ ComfyUI started (PID: {proc.pid})")
            
            # Wait for startup
            self.log("Waiting for ComfyUI to initialize...")
            time.sleep(5)
            
            return True
            
        except Exception as e:
            self.log(f"Failed to start ComfyUI: {e}", "ERROR")
            return False
    
    def start_ollama(self):
        """Start Ollama LLM server"""
        if self.is_linux:
            self.log("Running in Linux VM - Ollama cannot start here", "WARN")
            return True
        
        self.banner("STARTING OLLAMA SERVER")
        
        try:
            self.log("Launching Ollama...")
            
            proc = subprocess.Popen(
                "ollama serve",
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
            )
            
            self.processes.append(proc)
            self.log(f"✓ Ollama started (PID: {proc.pid})")
            time.sleep(3)
            
            return True
            
        except Exception as e:
            self.log(f"Failed to start Ollama: {e}", "ERROR")
            return False
    
    def start_kokoro(self):
        """Start Kokoro TTS server"""
        if self.is_linux:
            self.log("Running in Linux VM - Kokoro cannot start here", "WARN")
            return True
        
        self.banner("STARTING KOKORO TTS SERVER")
        
        if not self.kokoro_path.exists():
            self.log(f"Kokoro not found at {self.kokoro_path}", "WARN")
            return True
        
        try:
            self.log(f"Launching Kokoro from {self.kokoro_path}")
            
            proc = subprocess.Popen(
                [sys.executable, "run_api_server.py"],
                cwd=str(self.kokoro_path),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
            )
            
            self.processes.append(proc)
            self.log(f"✓ Kokoro started (PID: {proc.pid})")
            time.sleep(3)
            
            return True
            
        except Exception as e:
            self.log(f"Failed to start Kokoro: {e}", "WARN")
            return True  # Non-critical
    
    def run_generation(self):
        """Run EVAVO multi-modal generation tests"""
        self.banner("RUNNING MULTI-MODAL GENERATION")
        
        test_file = self.repo_path / "COMPLETE-MULTIMODAL-TEST.py"
        
        if not test_file.exists():
            self.log(f"Test file not found: {test_file}", "ERROR")
            return False
        
        try:
            os.chdir(self.repo_path)
            self.log(f"Working directory: {os.getcwd()}")
            self.log("Running COMPLETE-MULTIMODAL-TEST.py...")
            self.log("")
            
            result = subprocess.run(
                [sys.executable, "COMPLETE-MULTIMODAL-TEST.py"],
                timeout=3600,
                cwd=str(self.repo_path)
            )
            
            if result.returncode == 0:
                self.log("✓ Generation completed successfully")
                return True
            else:
                self.log(f"Generation failed with exit code {result.returncode}", "ERROR")
                return False
                
        except subprocess.TimeoutExpired:
            self.log("Generation timed out after 3600 seconds", "ERROR")
            return False
        except Exception as e:
            self.log(f"Error running generation: {e}", "ERROR")
            return False
    
    def copy_outputs(self):
        """Copy generated outputs to beestation"""
        self.banner("COPYING OUTPUTS TO BEESTATION")
        
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
        
        try:
            self.beestation.mkdir(parents=True, exist_ok=True)
            self.log(f"Beestation directory: {self.beestation}")
        except Exception as e:
            self.log(f"Failed to create beestation directory: {e}", "ERROR")
            return False
        
        success_count = 0
        for dir_name in output_dirs:
            src = self.repo_path / dir_name
            if src.exists():
                dst = self.beestation / dir_name
                try:
                    if dst.exists():
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                    file_count = len(list(dst.glob("**/*")))
                    self.log(f"✓ {dir_name}: {file_count} items")
                    success_count += 1
                except Exception as e:
                    self.log(f"✗ {dir_name}: {e}", "ERROR")
            else:
                self.log(f"  {dir_name}: directory not found")
        
        if success_count > 0:
            self.log(f"✓ Copied {success_count}/{len(output_dirs)} output directories")
            return True
        
        return False
    
    def cleanup(self):
        """Clean up processes"""
        self.log("Cleaning up processes...")
        for proc in self.processes:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except:
                try:
                    proc.kill()
                except:
                    pass
    
    def run(self, mode="full"):
        """Execute automation workflow"""
        self.banner("EVAVO FULLY AUTOMATED GENERATION SYSTEM")
        self.log(f"Platform: {self.platform}")
        self.log(f"Mode: {mode}")
        self.log(f"Start time: {self.start_time}")
        self.log("")
        
        try:
            # Verify paths
            if not self.verify_paths():
                return 1
            
            if mode in ["full", "test"]:
                # Start services (non-blocking in Linux VM)
                if not self.is_linux:
                    if not self.start_comfyui():
                        return 1
                    if not self.start_ollama():
                        return 1
                    if not self.start_kokoro():
                        return 1
            
            # Run generation
            if mode in ["full", "generate", "test"]:
                if not self.run_generation():
                    return 1
            
            # Copy outputs
            if mode == "full":
                if not self.copy_outputs():
                    self.log("Some outputs were not copied", "WARN")
            
            # Summary
            elapsed = (datetime.now() - self.start_time).total_seconds()
            self.banner("AUTOMATION COMPLETE!")
            self.log(f"Total runtime: {elapsed:.1f} seconds")
            self.log(f"Outputs: {self.beestation}")
            self.log("")
            
            return 0
            
        except KeyboardInterrupt:
            self.log("Interrupted by user", "WARN")
            return 1
        except Exception as e:
            self.log(f"Unexpected error: {e}", "ERROR")
            import traceback
            traceback.print_exc()
            return 1
        finally:
            self.cleanup()

def main():
    parser = argparse.ArgumentParser(
        description="EVAVO Fully Automated Multi-Modal Generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python EVAVO-AUTOMATION.py              # Full automation (start services + generate + copy)
  python EVAVO-AUTOMATION.py --mode test  # Run tests only (services must be running)
  python EVAVO-AUTOMATION.py --mode gen   # Generate only (services must be running)
        """
    )
    
    parser.add_argument(
        "--mode",
        choices=["full", "test", "generate"],
        default="full",
        help="Execution mode (default: full)"
    )
    
    args = parser.parse_args()
    
    automation = EVAVOAutomation()
    return automation.run(mode=args.mode)

if __name__ == "__main__":
    sys.exit(main())
