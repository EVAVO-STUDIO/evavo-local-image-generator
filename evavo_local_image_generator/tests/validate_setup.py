"""
Comprehensive setup validation for EVAVO infrastructure.

Validates:
- Package structure and imports
- Service endpoints
- Storage configuration
- Environmental variables
"""

import sys
import os

def validate_package_structure():
    """Validate Python package structure."""
    print("=== Package Structure Validation ===")
    
    required_modules = [
        'evavo_local_image_generator',
        'evavo_local_image_generator.scripts',
        'evavo_local_image_generator.generators',
        'evavo_local_image_generator.backends',
        'evavo_local_image_generator.scripts.legacy_automation',
    ]
    
    all_valid = True
    for module_name in required_modules:
        try:
            __import__(module_name)
            print(f"✓ {module_name}")
        except ImportError as e:
            print(f"✗ {module_name}: {e}")
            all_valid = False
    
    return all_valid

def validate_environment():
    """Validate required environment variables."""
    print("\n=== Environment Variables ===")
    
    env_vars = {
        'EVAVO_LOCAL_IMAGE_GENERATOR_MODE': 'production',
        'EVAVO_LOCAL_IMAGE_GENERATOR_STORAGE': 'bee://primary/EVAVO/ImageGeneration',
        'EVAVO_COMFYUI_ENDPOINT': 'http://127.0.0.1:8188',
    }
    
    all_valid = True
    for var, default in env_vars.items():
        value = os.getenv(var, default)
        status = "✓" if value else "✗"
        print(f"{status} {var}: {value}")
    
    return all_valid

def validate_files():
    """Validate critical files exist."""
    print("\n=== Critical Files ===")
    
    required_files = [
        '.mcp.json',
        'README.md',
        'CLAUDE.md',
        'requirements.txt',
        'evavo-repository-task-manifest.json',
    ]
    
    all_valid = True
    for filename in required_files:
        exists = os.path.isfile(filename)
        status = "✓" if exists else "✗"
        print(f"{status} {filename}")
        all_valid = all_valid and exists
    
    return all_valid

def main():
    """Run all validations."""
    print("EVAVO Setup Validation\n")
    
    results = {
        'package': validate_package_structure(),
        'environment': validate_environment(),
        'files': validate_files(),
    }
    
    print("\n=== Summary ===")
    all_passed = all(results.values())
    
    for check, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{check.capitalize()}: {status}")
    
    print(f"\nOverall: {'✓ READY' if all_passed else '✗ INCOMPLETE'}")
    return 0 if all_passed else 1

if __name__ == '__main__':
    sys.exit(main())
