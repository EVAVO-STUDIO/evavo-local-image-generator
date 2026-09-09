"""Read-only registry of historical EVAVO launcher filenames.

The current production path is native-ComfyUI image generation through the
canonical controller/MCP tools. Historical launcher files are retained as safe
compatibility shims where useful; this module only inventories names for
provenance/debugging and never executes them or maps them to unsupported
modalities.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional


class LegacyScriptRegistry:
    """Read-only inventory of historical launcher-style scripts."""

    def __init__(self, scripts_dir: Optional[Path] = None):
        self.scripts_dir = scripts_dir or Path(__file__).resolve().parents[3]
        self.scripts: Dict[str, Path] = {}
        self._scan_scripts()

    def _scan_scripts(self) -> None:
        for pattern in ("*.py", "*.ps1", "*.bat", "*.sh"):
            for script in self.scripts_dir.glob(pattern):
                if script.name.startswith(("AUTO", "RUN", "LAUNCH", "EXECUTE", "START", "TEST", "DEMO", "COMPLETE")):
                    self.scripts[script.stem.lower()] = script.resolve()

    def list_scripts(self) -> List[str]:
        return sorted(self.scripts)

    def get_script(self, name: str) -> Optional[Path]:
        """Return the file path only; callers must not treat this as execution authority."""
        return self.scripts.get(str(name).lower())


if __name__ == "__main__":
    registry = LegacyScriptRegistry()
    print(f"Found {len(registry.scripts)} historical launcher files:")
    for script_name in registry.list_scripts():
        print(f"  - {script_name}")
