"""Offline contract tests for the canonical frozen release entrypoint."""

from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class ReleaseEntrypointContractTests(unittest.TestCase):
    def test_release_requires_explicit_checkpoint_and_masks_image_environment(self):
        source = (ROOT / "RUN-RELEASE.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("[Parameter(Mandatory = $true)]", source)
        self.assertIn("[string]$Checkpoint", source)
        self.assertIn("EVAVO_IMAGE_QUALITY_PROFILE", source)
        self.assertIn("EVAVO_IMAGE_LORA", source)
        self.assertIn("EVAVO_COMFYUI_WORKFLOW", source)
        self.assertIn("environmentValuesRecorded = $false", source)
        self.assertIn("RUN-FULL-QUALITY-RELEASE.ps1", source)
        self.assertIn("release-policy.json", source)
        self.assertIn("release-evidence.py create", source)
        self.assertIn("release-evidence.py verify", source)
        self.assertIn("FINALIZE-FULL-RELEASE.ps1", source)

    def test_release_restores_process_environment(self):
        source = (ROOT / "RUN-RELEASE.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("finally", source)
        self.assertIn("$previous.GetEnumerator()", source)
        self.assertIn("SetEnvironmentVariable", source)

    def test_release_script_parses_when_powershell_is_available(self):
        executable = next(
            (
                value
                for name in ("pwsh.exe", "powershell.exe", "pwsh", "powershell")
                if (value := shutil.which(name))
            ),
            None,
        )
        if executable is None:
            self.skipTest("PowerShell is not available in this environment")
        path = (ROOT / "RUN-RELEASE.ps1").resolve()
        escaped = str(path).replace("'", "''")
        command = (
            "$tokens=$null; $errors=$null; "
            f"[System.Management.Automation.Language.Parser]::ParseFile('{escaped}', [ref]$tokens, [ref]$errors) | Out-Null; "
            "if ($errors.Count -gt 0) { $errors | ForEach-Object { Write-Error $_.Message }; exit 1 }; exit 0"
        )
        result = subprocess.run(
            [executable, "-NoProfile", "-NonInteractive", "-Command", command],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
