"""Contract checks for the Windows GPU quality benchmark runner."""

from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class GpuQualityRunnerTests(unittest.TestCase):
    def test_runner_keeps_performance_and_visual_evidence_together(self):
        source = (ROOT / "RUN-GPU-QUALITY-BENCHMARK.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("gpu-quality-benchmark.py", source)
        self.assertIn("quality-report.py", source)
        self.assertIn("runtime-snapshot.py", source)
        self.assertIn("human_review.csv", source)
        self.assertIn("Performance evidence alone never promotes a profile", source)
        self.assertIn("IsPathRooted", source)

    def test_runner_parses_when_powershell_is_available(self):
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
        path = (ROOT / "RUN-GPU-QUALITY-BENCHMARK.ps1").resolve()
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
