#!/usr/bin/env python3
"""
EVAVO Comprehensive AI Systems Testing & Optimization Suite
Tests all AI models, services, and integrations on local platform
"""

import subprocess
import requests
import time
import json
import sys
from datetime import datetime
from pathlib import Path

class AISystemsTester:
    def __init__(self):
        self.results = {}
        self.start_time = datetime.now()
        self.comfyui_url = "http://127.0.0.1:8188"
        self.kokoro_url = "http://127.0.0.1:8000"
        self.ollama_url = "http://127.0.0.1:11434"
        
    def log(self, level, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [{level:8s}] {message}")
    
    def banner(self, title):
        border = "=" * 70
        print(f"\n{border}")
        print(f"  {title}")
        print(f"{border}\n")
    
    def save_results(self):
        """Save test results to JSON"""
        output_file = Path("ai-systems-test-results.json")
        with open(output_file, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        self.log("INFO", f"Results saved to {output_file}")
    
    # ==================== COMFYUI TESTS ====================
    
    def test_comfyui_health(self):
        """Test ComfyUI server health and connectivity"""
        self.banner("TEST 1: COMFYUI SERVER HEALTH")
        
        try:
            response = requests.get(f"{self.comfyui_url}/system_stats", timeout=5)
            if response.status_code == 200:
                stats = response.json()
                self.log("SUCCESS", "✓ ComfyUI is running")
                self.log("INFO", f"  GPU Memory: {stats.get('ram', {}).get('used', 'N/A')} MB used")
                self.results['comfyui_health'] = {
                    'status': 'running',
                    'stats': stats
                }
                return True
        except Exception as e:
            self.log("ERROR", f"✗ ComfyUI not responding: {e}")
            self.results['comfyui_health'] = {'status': 'not_running', 'error': str(e)}
            return False
    
    def test_comfyui_models(self):
        """Test available models in ComfyUI"""
        self.banner("TEST 2: COMFYUI AVAILABLE MODELS")
        
        try:
            response = requests.get(f"{self.comfyui_url}/models", timeout=10)
            if response.status_code == 200:
                models = response.json()
                
                self.log("SUCCESS", "✓ Model list retrieved")
                self.log("INFO", f"  Checkpoints: {len(models.get('checkpoints', []))}")
                self.log("INFO", f"  VAE: {len(models.get('vae', []))}")
                self.log("INFO", f"  LoRAs: {len(models.get('loras', []))}")
                self.log("INFO", f"  Upscalers: {len(models.get('upscale_models', []))}")
                self.log("INFO", f"  Embeddings: {len(models.get('embeddings', []))}")
                
                self.results['comfyui_models'] = {
                    'status': 'success',
                    'counts': {
                        'checkpoints': len(models.get('checkpoints', [])),
                        'vae': len(models.get('vae', [])),
                        'loras': len(models.get('loras', [])),
                        'upscalers': len(models.get('upscale_models', [])),
                        'embeddings': len(models.get('embeddings', []))
                    }
                }
                return True
        except Exception as e:
            self.log("ERROR", f"✗ Failed to retrieve models: {e}")
            self.results['comfyui_models'] = {'status': 'error', 'error': str(e)}
            return False
    
    def test_comfyui_queue(self):
        """Test ComfyUI queue system"""
        self.banner("TEST 3: COMFYUI QUEUE SYSTEM")
        
        try:
            response = requests.get(f"{self.comfyui_url}/queue", timeout=5)
            if response.status_code == 200:
                queue = response.json()
                
                self.log("SUCCESS", "✓ Queue system operational")
                self.log("INFO", f"  Queue size: {len(queue.get('queue_pending', []))}")
                self.log("INFO", f"  Processing: {len(queue.get('queue_running', []))}")
                
                self.results['comfyui_queue'] = {
                    'status': 'operational',
                    'queue_info': queue
                }
                return True
        except Exception as e:
            self.log("ERROR", f"✗ Queue system error: {e}")
            self.results['comfyui_queue'] = {'status': 'error', 'error': str(e)}
            return False
    
    # ==================== KOKORO TTS TESTS ====================
    
    def test_kokoro_health(self):
        """Test Kokoro text-to-speech service"""
        self.banner("TEST 4: KOKORO TEXT-TO-SPEECH")
        
        try:
            response = requests.get(f"{self.kokoro_url}/health", timeout=5)
            if response.status_code == 200:
                self.log("SUCCESS", "✓ Kokoro TTS is running")
                self.results['kokoro_health'] = {'status': 'running'}
                return True
        except requests.exceptions.ConnectionError:
            self.log("WARNING", "⚠ Kokoro TTS not running (optional)")
            self.results['kokoro_health'] = {'status': 'not_running'}
            return False
        except Exception as e:
            self.log("ERROR", f"✗ Kokoro error: {e}")
            self.results['kokoro_health'] = {'status': 'error', 'error': str(e)}
            return False
    
    # ==================== OLLAMA TESTS ====================
    
    def test_ollama_health(self):
        """Test Ollama LLM service"""
        self.banner("TEST 5: OLLAMA LOCAL LLM")
        
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                data = response.json()
                models = data.get('models', [])
                
                self.log("SUCCESS", "✓ Ollama is running")
                self.log("INFO", f"  Installed models: {len(models)}")
                
                for model in models[:5]:
                    self.log("INFO", f"    - {model.get('name', 'unknown')}")
                
                self.results['ollama_health'] = {
                    'status': 'running',
                    'model_count': len(models),
                    'models': [m.get('name') for m in models]
                }
                return True
        except requests.exceptions.ConnectionError:
            self.log("WARNING", "⚠ Ollama not running (optional)")
            self.results['ollama_health'] = {'status': 'not_running'}
            return False
        except Exception as e:
            self.log("ERROR", f"✗ Ollama error: {e}")
            self.results['ollama_health'] = {'status': 'error', 'error': str(e)}
            return False
    
    # ==================== EVAVO IMAGE GEN TESTS ====================
    
    def test_evavo_image_generation_ready(self):
        """Test EVAVO image generation system"""
        self.banner("TEST 6: EVAVO IMAGE GENERATION SYSTEM")
        
        try:
            from claude_control import ClaudeController
            
            controller = ClaudeController()
            self.log("SUCCESS", "✓ ClaudeController initialized")
            
            # Try system check
            status = controller.check_system()
            if status.get('status') == 'error':
                self.log("WARNING", "⚠ ComfyUI not ready yet (expected if not started)")
                self.results['evavo_image_gen'] = {
                    'status': 'controller_ready',
                    'system_check': status
                }
            else:
                self.log("SUCCESS", "✓ System ready for generation")
                self.results['evavo_image_gen'] = {
                    'status': 'ready',
                    'system_check': status
                }
            return True
            
        except Exception as e:
            self.log("ERROR", f"✗ Image generation error: {e}")
            self.results['evavo_image_gen'] = {'status': 'error', 'error': str(e)}
            return False
    
    # ==================== INTEGRATION TESTS ====================
    
    def test_mcp_server(self):
        """Test MCP server status"""
        self.banner("TEST 7: MCP SERVER INTEGRATION")
        
        try:
            # Check if MCP bridge files exist
            mcp_bridge = Path("mcp_bridge.py")
            mcp_server = Path("image-generation-mcp.mjs")
            
            if mcp_bridge.exists() and mcp_server.exists():
                self.log("SUCCESS", "✓ MCP server files present")
                self.log("INFO", f"  mcp_bridge.py: {mcp_bridge.stat().st_size} bytes")
                self.log("INFO", f"  image-generation-mcp.mjs: {mcp_server.stat().st_size} bytes")
                
                self.results['mcp_server'] = {
                    'status': 'files_present',
                    'files': {
                        'mcp_bridge': str(mcp_bridge),
                        'mcp_server': str(mcp_server)
                    }
                }
                return True
            else:
                self.log("WARNING", "⚠ Some MCP files missing")
                self.results['mcp_server'] = {'status': 'incomplete'}
                return False
                
        except Exception as e:
            self.log("ERROR", f"✗ MCP check error: {e}")
            self.results['mcp_server'] = {'status': 'error', 'error': str(e)}
            return False
    
    def test_dependencies(self):
        """Test Python dependencies"""
        self.banner("TEST 8: PYTHON DEPENDENCIES")
        
        required_packages = [
            'requests', 'pillow', 'aiohttp', 'python-dotenv', 'numpy'
        ]
        
        try:
            result = subprocess.run(
                ['pip', 'list'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            installed = result.stdout
            missing = []
            found = []
            
            for pkg in required_packages:
                if pkg.lower() in installed.lower():
                    found.append(pkg)
                    self.log("SUCCESS", f"  ✓ {pkg}")
                else:
                    missing.append(pkg)
                    self.log("ERROR", f"  ✗ {pkg} (missing)")
            
            self.results['dependencies'] = {
                'status': 'checked',
                'found': found,
                'missing': missing
            }
            
            return len(missing) == 0
            
        except Exception as e:
            self.log("ERROR", f"✗ Dependency check error: {e}")
            self.results['dependencies'] = {'status': 'error', 'error': str(e)}
            return False
    
    # ==================== PERFORMANCE TESTS ====================
    
    def test_performance(self):
        """Test system performance metrics"""
        self.banner("TEST 9: SYSTEM PERFORMANCE")
        
        try:
            import psutil
            
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            
            self.log("INFO", f"  CPU Usage: {cpu_percent}%")
            self.log("INFO", f"  Memory: {memory.percent}% ({memory.used / (1024**3):.1f} GB / {memory.total / (1024**3):.1f} GB)")
            
            if psutil.disk_usage:
                disk = psutil.disk_usage('/')
                self.log("INFO", f"  Disk: {disk.percent}% ({disk.used / (1024**3):.1f} GB / {disk.total / (1024**3):.1f} GB)")
            
            self.results['performance'] = {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_available_gb': (memory.available / (1024**3))
            }
            return True
            
        except ImportError:
            self.log("WARNING", "⚠ psutil not installed (optional)")
            return True
        except Exception as e:
            self.log("ERROR", f"✗ Performance test error: {e}")
            self.results['performance'] = {'status': 'error', 'error': str(e)}
            return False
    
    def run_all_tests(self):
        """Run complete test suite"""
        self.banner("EVAVO AI SYSTEMS - COMPREHENSIVE TEST SUITE")
        
        tests = [
            ("ComfyUI Health", self.test_comfyui_health),
            ("ComfyUI Models", self.test_comfyui_models),
            ("ComfyUI Queue", self.test_comfyui_queue),
            ("Kokoro TTS", self.test_kokoro_health),
            ("Ollama LLM", self.test_ollama_health),
            ("Image Generation", self.test_evavo_image_generation_ready),
            ("MCP Server", self.test_mcp_server),
            ("Dependencies", self.test_dependencies),
            ("Performance", self.test_performance),
        ]
        
        passed = 0
        failed = 0
        
        for test_name, test_func in tests:
            try:
                if test_func():
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                self.log("ERROR", f"Test '{test_name}' crashed: {e}")
                failed += 1
        
        # Summary
        self.banner("TEST SUMMARY")
        self.log("INFO", f"Passed: {passed}/{len(tests)}")
        self.log("INFO", f"Failed: {failed}/{len(tests)}")
        
        if failed == 0:
            self.log("SUCCESS", "✓ All systems operational!")
        else:
            self.log("WARNING", f"⚠ {failed} system(s) need attention")
        
        # Save results
        self.save_results()
        
        elapsed = (datetime.now() - self.start_time).total_seconds()
        self.log("INFO", f"Test duration: {elapsed:.1f} seconds")

if __name__ == "__main__":
    tester = AISystemsTester()
    tester.run_all_tests()
