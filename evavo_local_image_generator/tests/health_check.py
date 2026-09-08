"""
Health check utilities for EVAVO services.

Validates that required backend services are running and accessible.
"""

import asyncio
import json
from typing import Dict
import httpx

class HealthChecker:
    """Check health of EVAVO backend services."""
    
    SERVICES = {
        'comfyui': 'http://127.0.0.1:8188/api/models',
        'ollama': 'http://127.0.0.1:11434/api/tags',
        'kokoro': 'http://127.0.0.1:8000/docs',
    }
    
    @classmethod
    async def check_all(cls) -> Dict[str, bool]:
        """Check all services."""
        results = {}
        async with httpx.AsyncClient(timeout=5.0) as client:
            for service, url in cls.SERVICES.items():
                try:
                    response = await client.get(url)
                    results[service] = response.status_code < 400
                except Exception as e:
                    results[service] = False
        return results
    
    @classmethod
    def run_sync(cls) -> Dict[str, bool]:
        """Synchronous wrapper for health check."""
        return asyncio.run(cls.check_all())

def print_health_report():
    """Print health check report."""
    print("=== EVAVO Service Health Check ===")
    results = HealthChecker.run_sync()
    
    for service, healthy in results.items():
        status = "✓ Running" if healthy else "✗ Not responding"
        print(f"{service:10} {status}")
    
    all_healthy = all(results.values())
    print(f"\nOverall: {'✓ All services healthy' if all_healthy else '✗ Some services offline'}")
    return all_healthy

if __name__ == '__main__':
    print_health_report()
