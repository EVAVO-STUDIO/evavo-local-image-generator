#!/usr/bin/env python3
"""
Batch image generation utility for EVAVO Local Image Generator.
Queues multiple generation tasks and displays results.
"""

import asyncio
import json
import subprocess
import sys
from datetime import datetime
from typing import List, Dict, Any

# Example prompts for batch generation
EXAMPLE_PROMPTS = [
    "A serene landscape with mountains and a sunset",
    "A futuristic cyberpunk city with neon lights",
    "An underwater scene with coral and tropical fish",
    "A cozy cabin in a snowy forest",
    "An abstract digital art piece with geometric shapes"
]

async def queue_generation(prompt: str, project_name: str = "batch_gen") -> Dict[str, Any]:
    """Queue a single generation task."""
    try:
        result = subprocess.run(
            ["python", "evavo-wrapper.py", "generate_image", 
             json.dumps({"prompt": prompt, "project_name": project_name})],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            return {"status": "error", "message": result.stderr}
    except Exception as e:
        return {"status": "error", "message": str(e)}

async def batch_generate(prompts: List[str], project_name: str = "batch_gen") -> List[Dict[str, Any]]:
    """Generate multiple images concurrently."""
    tasks = [queue_generation(prompt, project_name) for prompt in prompts]
    return await asyncio.gather(*tasks)

def display_results(results: List[Dict[str, Any]], prompts: List[str]):
    """Display batch results in formatted table."""
    print("\n" + "="*80)
    print(f"BATCH GENERATION RESULTS ({datetime.now().isoformat()})")
    print("="*80)
    print(f"{'#':<3} {'Status':<10} {'Task ID':<36} {'Prompt':<30}")
    print("-"*80)
    
    for i, (result, prompt) in enumerate(zip(results, prompts), 1):
        status = result.get("status", "unknown")
        task_id = result.get("task_id", "N/A")[:36]
        prompt_short = prompt[:30]
        print(f"{i:<3} {status:<10} {task_id:<36} {prompt_short:<30}")
    
    print("="*80)

def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Batch image generation for EVAVO")
    parser.add_argument("--prompts", nargs="+", help="Custom prompts to generate")
    parser.add_argument("--project", default="batch_gen", help="Project name")
    parser.add_argument("--examples", action="store_true", help="Use example prompts")
    
    args = parser.parse_args()
    
    # Determine prompts to use
    if args.prompts:
        prompts = args.prompts
    elif args.examples or len(sys.argv) == 1:
        prompts = EXAMPLE_PROMPTS
    else:
        print("No prompts provided. Use --prompts or --examples")
        sys.exit(1)
    
    print(f"Queuing {len(prompts)} generation tasks...")
    
    # Run batch generation
    results = asyncio.run(batch_generate(prompts, args.project))
    
    # Display results
    display_results(results, prompts)
    
    # Summary
    successful = sum(1 for r in results if r.get("status") == "queued")
    print(f"\n✓ {successful}/{len(prompts)} tasks queued successfully")

if __name__ == "__main__":
    main()
