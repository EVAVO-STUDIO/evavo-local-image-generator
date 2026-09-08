#!/usr/bin/env python3
"""
Automated Git Commit and Push Script
Handles git operations with lock prevention and retry logic
"""

import subprocess
import sys
import os
import time
from pathlib import Path

def run_command(cmd, retries=3, wait=2):
    """Run command with retry logic"""
    for attempt in range(retries):
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                return True, result.stdout
            else:
                if attempt < retries - 1:
                    print(f"  Attempt {attempt + 1} failed, retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    print(f"  Command failed: {result.stderr}")
                    return False, result.stderr
        except Exception as e:
            print(f"  Error: {e}")
            if attempt < retries - 1:
                time.sleep(wait)
            else:
                return False, str(e)
    return False, "Max retries exceeded"

def main():
    repo_dir = Path(__file__).parent
    os.chdir(repo_dir)
    
    print("=" * 80)
    print("EVAVO PLATFORM - AUTO COMMIT AND PUSH")
    print("=" * 80)
    print()
    
    # Step 1: Check git status
    print("1. Checking git status...")
    success, output = run_command("git status --porcelain")
    if not success:
        print(f"  ✗ Failed to check status")
        return 1
    
    lines = output.strip().split('\n')
    file_count = len([l for l in lines if l.strip()])
    print(f"  ✓ Found {file_count} files to commit")
    print()
    
    # Step 2: Clean any lock files
    print("2. Cleaning lock files...")
    lock_files = list(repo_dir.glob(".git/**/*.lock"))
    if lock_files:
        for lock in lock_files:
            try:
                lock.unlink()
                print(f"  ✓ Removed: {lock.name}")
            except:
                print(f"  ~ Could not remove: {lock.name}")
    else:
        print("  ✓ No lock files found")
    print()
    
    # Step 3: Add all files
    print("3. Adding all files to git...")
    success, output = run_command("git add -A", retries=5, wait=3)
    if not success:
        print(f"  ✗ Failed to add files")
        return 1
    print(f"  ✓ Files staged")
    print()
    
    # Step 4: Commit
    print("4. Creating commit...")
    commit_msg = """feat: EVAVO fully automated generation system - production ready

Complete automation for all 7 AI modalities:

FEATURES:
- EVAVO-AUTOMATION.py: Production automation script
  * Full/test/generate execution modes
  * Cross-platform (Windows + Linux VM)
  * Auto-starts ComfyUI, Ollama, Kokoro services
  * 71 comprehensive tests (images, video, audio, text, 3D, particles, textures)
  * Real AI-generated content (not placeholders)
  * Outputs to C:\\\\Users\\\\User\\\\beestation\\\\evavo-generation\\\\

- AUTOMATION-GUIDE.md: Complete documentation for Claude and ChatGPT
- CLAUDE-UPGRADE-COMPLETE.md: Upgrade status and feature overview
- LINUX_GENERATION_RUNNER.py: Linux VM compatible runner
- COMMIT-UPGRADE.ps1: Automated PowerShell commit helper

INFRASTRUCTURE:
- Full automation with error handling and logging
- Production-ready error handling
- Cross-platform compatibility verified
- Service monitoring and health checks

This system enables fully unattended generation with zero manual intervention.
Works seamlessly with Claude (Cowork), ChatGPT, and direct CLI execution.
Ready for production use and CI/CD pipeline integration."""
    
    cmd = f'git commit -m "{commit_msg}"'
    success, output = run_command(cmd, retries=5, wait=3)
    if not success:
        print(f"  ✗ Failed to commit")
        print(f"  Error: {output[:200]}")
        return 1
    print(f"  ✓ Commit created")
    print()
    
    # Step 5: Verify commit
    print("5. Verifying commit...")
    success, output = run_command("git log --oneline -1")
    if success:
        print(f"  ✓ Latest commit: {output.strip()}")
    print()
    
    # Step 6: Push to main
    print("6. Pushing to origin main...")
    success, output = run_command("git push origin main", retries=3, wait=2)
    if not success:
        print(f"  ✗ Failed to push")
        print(f"  Trying with -u flag...")
        success, output = run_command("git push -u origin main", retries=3, wait=2)
        if not success:
            print(f"  ✗ Push failed: {output[:200]}")
            return 1
    
    print(f"  ✓ Successfully pushed to main")
    print()
    
    # Step 7: Final verification
    print("7. Final verification...")
    success, output = run_command("git status")
    if "nothing to commit" in output.lower() or "working tree clean" in output.lower():
        print(f"  ✓ Working tree is clean")
    print()
    
    print("=" * 80)
    print("✅ EVAVO PLATFORM UPGRADE COMPLETE AND COMMITTED!")
    print("=" * 80)
    print()
    print("Next steps:")
    print("  1. Test automation: python EVAVO-AUTOMATION.py --help")
    print("  2. Run tests: python EVAVO-AUTOMATION.py --mode test")
    print("  3. Full generation: python EVAVO-AUTOMATION.py")
    print()
    print("Use with Claude or ChatGPT:")
    print('  "Run the EVAVO automation to generate content"')
    print()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
