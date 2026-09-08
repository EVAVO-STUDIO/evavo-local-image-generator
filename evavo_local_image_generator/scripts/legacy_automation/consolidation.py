"""
Legacy Script Consolidation and Migration Guide

This module provides utilities for running legacy automation scripts
while gradually migrating them to the modern EVAVO infrastructure.

The legacy scripts in the parent directory are being consolidated as:
1. Reference implementations
2. Test fixtures for validation
3. Data providers for pipeline integration

Status Summary:
- Total legacy scripts: 48+
- Python scripts: 15+
- PowerShell scripts: 8+
- Batch/Shell scripts: 5+

Migration Strategy:
Each legacy script's functionality is being mapped to one of:
- image_generation (ComfyUI workflows)
- video_generation (animated outputs)
- audio_generation (text-to-speech, music)
- 3d_model_generation (3D asset creation)
- texture_generation (PBR textures)
- particle_generation (particle systems)

See CONSOLIDATION.md for detailed mapping.
"""

import os
import subprocess
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class LegacyScriptRegistry:
    """Registry of legacy automation scripts for gradual migration."""
    
    def __init__(self, scripts_dir: Optional[Path] = None):
        self.scripts_dir = scripts_dir or Path(__file__).parent.parent.parent
        self.scripts: Dict[str, Path] = {}
        self._scan_scripts()
    
    def _scan_scripts(self):
        """Scan for legacy automation scripts."""
        for pattern in ['*.py', '*.ps1', '*.bat', '*.sh']:
            for script in self.scripts_dir.glob(pattern):
                if script.name.startswith(('AUTO', 'RUN', 'LAUNCH', 'EXECUTE', 'START', 'TEST', 'DEMO', 'COMPLETE')):
                    key = script.stem.lower()
                    self.scripts[key] = script
    
    def list_scripts(self) -> List[str]:
        """List all registered legacy scripts."""
        return sorted(self.scripts.keys())
    
    def get_script(self, name: str) -> Optional[Path]:
        """Get a script by name."""
        return self.scripts.get(name.lower())

if __name__ == '__main__':
    registry = LegacyScriptRegistry()
    print(f"Found {len(registry.scripts)} legacy scripts:")
    for script_name in registry.list_scripts():
        print(f"  - {script_name}")
