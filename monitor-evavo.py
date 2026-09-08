#!/usr/bin/env python3
"""
Real-time system health monitoring for EVAVO Local Image Generator.
Checks ComfyUI endpoint and EVAVO wrapper functionality.
"""

import asyncio
import json
import subprocess
import time
from datetime import datetime
import sys

async def check_comfyui_health(endpoint: str = "http://127.0.0.1:8188") -> bool:
    """Check if ComfyUI endpoint is responsive."""
    try:
        result = subprocess.run(
            ["curl", "-s", "-m", "5", f"{endpoint}/system"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False

async def check_evavo_wrapper() -> bool:
    """Check if EVAVO wrapper is functional."""
    try:
        result = subprocess.run(
            ["python", "evavo-wrapper.py", "health_check", "{}"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False

async def run_health_check() -> dict:
    """Run comprehensive health check."""
    comfyui_ok = await check_comfyui_health()
    evavo_ok = await check_evavo_wrapper()
    
    return {
        "timestamp": datetime.now().isoformat(),
        "comfyui": "✓ OK" if comfyui_ok else "✗ OFFLINE",
        "evavo_wrapper": "✓ OK" if evavo_ok else "✗ ERROR",
        "overall": "✓ OPERATIONAL" if (comfyui_ok and evavo_ok) else "⚠ DEGRADED"
    }

async def monitor_continuous(interval: int = 10):
    """Monitor system health continuously."""
    print("Starting continuous monitoring (Ctrl+C to stop)...\n")
    
    try:
        while True:
            health = await run_health_check()
            
            # Clear screen (works on both Windows and Linux)
            subprocess.run("cls || clear", shell=True)
            
            print("="*50)
            print("EVAVO LOCAL IMAGE GENERATOR - SYSTEM STATUS")
            print("="*50)
            print(f"Time: {health['timestamp']}")
            print(f"\nComfyUI Endpoint: {health['comfyui']}")
            print(f"EVAVO Wrapper:    {health['evavo_wrapper']}")
            print(f"\nOverall Status:   {health['overall']}")
            print("="*50)
            print(f"Next check in {interval}s (Ctrl+C to stop)")
            
            await asyncio.sleep(interval)
            
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")

def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Monitor EVAVO system health")
    parser.add_argument("--continuous", action="store_true", help="Continuous monitoring")
    parser.add_argument("--interval", type=int, default=10, help="Check interval in seconds")
    
    args = parser.parse_args()
    
    if args.continuous:
        asyncio.run(monitor_continuous(args.interval))
    else:
        health = asyncio.run(run_health_check())
        print(json.dumps(health, indent=2))

if __name__ == "__main__":
    main()
