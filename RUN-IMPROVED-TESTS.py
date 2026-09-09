#!/usr/bin/env python3
"""
IMPROVED COMFYUI GENERATION TESTS
Quality fixes:
- Steps: 5 → 25-30 (major quality improvement)
- Resolution: 512x512 → 768x768  
- Better prompts with more detail
- Improved CFG values (8.0-8.5)
- Better negative prompts to avoid artifacts

This script generates 4 high-quality test images.
"""

import requests
import json
import time
import os
from datetime import datetime
from pathlib import Path

class HighQualityComfyTester:
    def __init__(self, base_url="http://127.0.0.1:8188"):
        self.base_url = base_url
        self.session = requests.Session()
        self.timeout = 600  # 10 minute timeout
        self.output_dir = Path("C:\\AI\\ComfyUI\\output")
        
    def health_check(self):
        """Verify ComfyUI server is running and healthy."""
        try:
            r = self.session.get(f"{self.base_url}/system_stats", timeout=10)
            if r.status_code == 200:
                stats = r.json()
                print(f"✓ ComfyUI is healthy and responding")
                return True
        except Exception as e:
            print(f"✗ Health check failed: {e}")
            print(f"   Make sure ComfyUI server is running on port 8188")
            return False
    
    def create_high_quality_workflow(self, positive_prompt, negative_prompt, seed, steps=28, cfg=8.2):
        """Create optimal 8-node workflow for SDXL."""
        workflow = {
            "1": {
                "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"},
                "class_type": "CheckpointLoaderSimple",
                "_meta": {"title": "Load Checkpoint"}
            },
            "2": {
                "inputs": {"text": positive_prompt, "clip": ["1", 1]},
                "class_type": "CLIPTextEncode",
                "_meta": {"title": "CLIP Text Encode (Positive)"}
            },
            "3": {
                "inputs": {"text": negative_prompt, "clip": ["1", 1]},
                "class_type": "CLIPTextEncode",
                "_meta": {"title": "CLIP Text Encode (Negative)"}
            },
            "4": {
                "inputs": {"height": 768, "width": 768, "batch_size": 1},
                "class_type": "EmptyLatentImage",
                "_meta": {"title": "Empty Latent Image (768x768)"}
            },
            "5": {
                "inputs": {
                    "seed": seed,
                    "steps": steps,  # ← KEY FIX: Was 5, now 25-30
                    "cfg": cfg,
                    "sampler_name": "euler",
                    "scheduler": "karras",
                    "denoise": 1.0,
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4", 0]
                },
                "class_type": "KSampler",
                "_meta": {"title": "KSampler (Improved)"}
            },
            "6": {
                "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
                "class_type": "VAEDecode",
                "_meta": {"title": "VAE Decode"}
            },
            "7": {
                "inputs": {"filename_prefix": "hq_gen", "images": ["6", 0]},
                "class_type": "SaveImage",
                "_meta": {"title": "Save Image"}
            }
        }
        return workflow
    
    def queue_prompt(self, workflow):
        """Queue workflow with proper API format."""
        payload = {"prompt": workflow}
        try:
            r = self.session.post(f"{self.base_url}/prompt", json=payload, timeout=self.timeout)
            if r.status_code == 200:
                result = r.json()
                prompt_id = result.get("prompt_id")
                return prompt_id
            else:
                print(f"  ✗ Queue error: {r.status_code} - {r.text[:200]}")
                return None
        except Exception as e:
            print(f"  ✗ Queue exception: {e}")
            return None
    
    def wait_for_completion(self, prompt_id, timeout=600):
        """Wait for generation to complete."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                r = self.session.get(f"{self.base_url}/history/{prompt_id}", timeout=10)
                if r.status_code == 200 and prompt_id in r.json():
                    return True
            except:
                pass
            time.sleep(3)
        return False
    
    def run_high_quality_tests(self):
        """Run improved generation tests."""
        print("\n" + "="*70)
        print("IMPROVED HIGH-QUALITY COMFYUI GENERATION TESTS")
        print("="*70)
        
        if not self.health_check():
            return False
        
        # High-quality test prompts with more detail
        tests = [
            {
                "name": "Epic Dragon",
                "positive": "A majestic dark fantasy dragon perched on ancient gothic ruins, intricate scales with metallic sheen, glowing golden eyes, dramatic cinematic lighting, volumetric fog, highly detailed, masterpiece, 8k quality, professional art",
                "negative": "blurry, low quality, distorted, deformed, artifacts, oversaturated, undersaturated, watermark",
                "seed": 42,
                "steps": 30,
                "cfg": 8.5
            },
            {
                "name": "Futuristic Logo",
                "positive": "Futuristic technology company logo, clean geometric design, neon blue and silver gradient, modern minimalist aesthetic, professional branding, vector style, sharp clean lines, high quality, 8k resolution",
                "negative": "blurry, messy, distorted, cluttered, low quality, artifacts, hand-drawn",
                "seed": 123,
                "steps": 28,
                "cfg": 8.2
            },
            {
                "name": "Medieval Knight",
                "positive": "Medieval knight in ornate golden armor, standing in misty enchanted forest, holding sword, dramatic backlighting, volumetric fog, detailed textures, cinematic dramatic lighting, masterpiece, professional art, 8k quality",
                "negative": "deformed, blurry, low quality, distorted proportions, artifacts, ugly",
                "seed": 789,
                "steps": 30,
                "cfg": 8.3
            },
            {
                "name": "Abstract Geometry",
                "positive": "Abstract geometric patterns, colorful vibrant tessellations, neon colors, mathematical precision, symmetrical composition, modern digital art, sharp clean details, high quality, professional",
                "negative": "blurry, distorted, low quality, chaotic, messy, artifacts",
                "seed": 456,
                "steps": 28,
                "cfg": 8.0
            }
        ]
        
        results = []
        print(f"\nGenerating {len(tests)} high-quality images...")
        print("(Each image will take 2-3 minutes with 28-30 steps)\n")
        
        for i, test in enumerate(tests, 1):
            print(f"[{i}/{len(tests)}] Generating: {test['name']}")
            print(f"     Steps: {test['steps']}, CFG: {test['cfg']}, Seed: {test['seed']}")
            
            workflow = self.create_high_quality_workflow(
                test['positive'],
                test['negative'],
                test['seed'],
                test['steps'],
                test['cfg']
            )
            
            prompt_id = self.queue_prompt(workflow)
            if not prompt_id:
                print(f"     ✗ Failed to queue prompt")
                results.append({"name": test['name'], "status": "queue_failed"})
                continue
            
            print(f"     ✓ Queued (ID: {prompt_id[:8]}...)")
            print(f"     Waiting for generation...")
            
            if self.wait_for_completion(prompt_id):
                print(f"     ✓ GENERATED SUCCESSFULLY!\n")
                results.append({
                    "name": test['name'],
                    "prompt_id": prompt_id,
                    "status": "success",
                    "steps": test['steps'],
                    "cfg": test['cfg']
                })
            else:
                print(f"     ✗ Generation timeout or failed\n")
                results.append({"name": test['name'], "status": "timeout"})
        
        # Save results
        output_file = Path("C:\\AI\\generation_tests\\hq_results.json")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json.dumps({
            "timestamp": datetime.now().isoformat(),
            "test_type": "high_quality_generation",
            "results": results
        }, indent=2))
        
        print("="*70)
        print("GENERATION COMPLETE")
        print("="*70)
        successful = sum(1 for r in results if r.get('status') == 'success')
        print(f"✓ Successfully generated: {successful}/{len(tests)} images")
        print(f"✓ Results saved to: {output_file}")
        print(f"✓ Images location: C:\\AI\\ComfyUI\\output\\")
        
        return successful == len(tests)

if __name__ == "__main__":
    print("\n" + "="*70)
    print("WAITING FOR COMFYUI SERVER")
    print("="*70)
    print("\nMake sure ComfyUI is running before proceeding.")
    print("Open a new terminal and run: RUN-IMPROVED-GENERATION-TEST.bat")
    print("\nPress ENTER when server is ready... (you'll see logs from ComfyUI)")
    
    input()
    
    tester = HighQualityComfyTester()
    tester.run_high_quality_tests()
