from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from evavo_local_image_generator import comfyui_runtime as runtime


class ComfyUIRuntimeTests(unittest.TestCase):
    def test_parent_level_portable_python_is_preferred_for_direct_comfyui_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            portable_root = Path(temp_dir)
            comfy_root = portable_root / "ComfyUI"
            comfy_root.mkdir()
            (comfy_root / "main.py").write_text("print('ok')\n", encoding="utf-8")
            embedded = portable_root / "python_embeded" / "python.exe"
            embedded.parent.mkdir()
            embedded.write_bytes(b"")

            with mock.patch.dict(os.environ, {"EVAVO_COMFYUI_PYTHON": "", "COMFYUI_PYTHON": ""}):
                install = runtime.inspect_install(comfy_root)

            self.assertIsNotNone(install)
            assert install is not None
            self.assertEqual(install.python, embedded.resolve())
            self.assertTrue(install.portable)
            self.assertEqual(install.workdir, comfy_root.resolve())

    def test_cpu_and_custom_node_isolation_flags_are_explicit(self) -> None:
        install = runtime.ComfyUIInstall(
            root=Path("C:/AI/ComfyUI"),
            python=Path("C:/AI/python_embeded/python.exe"),
            main_py=Path("C:/AI/ComfyUI/main.py"),
            portable=True,
        )
        command = install.command(cpu=True, disable_all_custom_nodes=True)
        self.assertEqual(command[0], str(install.python))
        self.assertEqual(command[1], "-s")
        self.assertEqual(command[2], str(install.main_py))
        self.assertIn("--cpu", command)
        self.assertIn("--disable-all-custom-nodes", command)
        self.assertIn("--windows-standalone-build", command)

    def test_source_install_does_not_add_portable_python_flag(self) -> None:
        install = runtime.ComfyUIInstall(
            root=Path("C:/AI/ComfyUI"),
            python=Path("C:/AI/ComfyUI/.venv/Scripts/python.exe"),
            main_py=Path("C:/AI/ComfyUI/main.py"),
            portable=False,
        )
        command = install.command(cpu=True)
        self.assertEqual(command[:2], [str(install.python), str(install.main_py)])
        self.assertNotIn("-s", command)
        self.assertNotIn("--windows-standalone-build", command)

    def test_missing_custom_node_dependency_is_classified(self) -> None:
        output = """Prestartup script for custom_nodes/example\nTraceback (most recent call last):\nModuleNotFoundError: No module named 'kornia'\n"""
        result = runtime.classify_startup_output(
            output,
            returncode=1,
            health_ready=False,
            timed_out=False,
        )
        self.assertEqual(result["category"], "custom_node_dependency")
        self.assertEqual(result["missing_modules"], ["kornia"])
        self.assertTrue(result["recommended_isolation"])

    def test_core_missing_dependency_is_classified_without_custom_node_signal(self) -> None:
        result = runtime.classify_startup_output(
            "ModuleNotFoundError: No module named 'torch'",
            returncode=1,
            health_ready=False,
            timed_out=False,
        )
        self.assertEqual(result["category"], "missing_dependency")
        self.assertEqual(result["missing_modules"], ["torch"])

    def test_windows_port_conflict_is_classified(self) -> None:
        result = runtime.classify_startup_output(
            "OSError: [WinError 10048] Only one usage of each socket address is normally permitted",
            returncode=1,
            health_ready=False,
            timed_out=False,
        )
        self.assertEqual(result["category"], "port_in_use")

    def test_alive_but_unhealthy_process_is_timeout(self) -> None:
        result = runtime.classify_startup_output(
            "Starting server initialization",
            returncode=None,
            health_ready=False,
            timed_out=True,
        )
        self.assertEqual(result["category"], "startup_timeout")


if __name__ == "__main__":
    unittest.main(verbosity=2)
