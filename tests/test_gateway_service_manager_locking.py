from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MANAGER_PATH = ROOT / "EVAVO-SERVICE-MANAGER.py"

try:
    import evavo_local_image_generator.comfyui_runtime  # noqa: F401
except ModuleNotFoundError:
    package = types.ModuleType("evavo_local_image_generator")
    runtime = types.ModuleType("evavo_local_image_generator.comfyui_runtime")
    runtime.ensure_comfyui = lambda *args, **kwargs: {"ok": True}
    runtime.native_health = lambda *args, **kwargs: {"ok": True}
    runtime.stop_managed_comfyui = lambda: {"stopped": False}
    sys.modules["evavo_local_image_generator"] = package
    sys.modules["evavo_local_image_generator.comfyui_runtime"] = runtime

spec = importlib.util.spec_from_file_location("evavo_gateway_service_manager_lock_test", MANAGER_PATH)
manager = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(manager)


@contextmanager
def always_busy(*args, **kwargs):
    raise TimeoutError("busy")
    yield  # pragma: no cover


class ServiceManagerLockingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patch = mock.patch.dict(os.environ, {}, clear=False)
        self.env_patch.start()
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        manager.STATE_DIR = base / "state"
        manager.STATE_FILE = manager.STATE_DIR / "service-manager.json"
        manager.STATE_IO_LOCK = manager.STATE_FILE.with_suffix(manager.STATE_FILE.suffix + ".lock")
        manager.LIFECYCLE_LOCK = manager.STATE_FILE.with_suffix(manager.STATE_FILE.suffix + ".lifecycle.lock")
        manager.TOKEN_FILE = manager.STATE_DIR / "3d-worker.token"
        manager.LOG_DIR = manager.STATE_DIR / "logs"

    def tearDown(self) -> None:
        self.temp.cleanup()
        self.env_patch.stop()

    def test_start_refuses_when_lifecycle_lock_is_busy_before_mutation(self) -> None:
        with (
            mock.patch.object(manager, "interprocess_lock", always_busy),
            mock.patch.object(manager, "configure_audio_provider") as audio,
            mock.patch.object(manager, "ensure_comfyui_service") as comfy,
            mock.patch.object(manager, "ensure_gateway_service") as gateway,
            self.assertRaises(RuntimeError) as context,
        ):
            manager.start_services()
        self.assertIn("SERVICE_MANAGER_BUSY", str(context.exception))
        audio.assert_not_called()
        comfy.assert_not_called()
        gateway.assert_not_called()

    def test_stop_refuses_when_lifecycle_lock_is_busy_before_process_mutation(self) -> None:
        with (
            mock.patch.object(manager, "interprocess_lock", always_busy),
            mock.patch.object(manager, "terminate_pid") as terminate,
            mock.patch.object(manager, "stop_managed_comfyui") as stop_native,
            self.assertRaises(RuntimeError) as context,
        ):
            manager.stop_services()
        self.assertIn("SERVICE_MANAGER_BUSY", str(context.exception))
        terminate.assert_not_called()
        stop_native.assert_not_called()

    def test_state_io_round_trip_uses_isolated_lock_and_atomic_file(self) -> None:
        payload = {"gateway": {"managed": True, "pid": 1234}}
        manager.save_state(payload)
        self.assertTrue(manager.STATE_FILE.is_file())
        self.assertEqual(manager.load_state(), payload)
        if os.name == "nt":
            self.assertFalse(manager.STATE_IO_LOCK.exists(), "Windows named mutexes should not leave fresh .lock artifacts")
        else:
            self.assertTrue(manager.STATE_IO_LOCK.is_file())

    def test_health_reports_busy_state_without_mutating_file(self) -> None:
        manager.STATE_DIR.mkdir(parents=True, exist_ok=True)
        manager.STATE_FILE.write_text('{"gateway":{"managed":true}}\n', encoding="utf-8")
        before = manager.STATE_FILE.read_text(encoding="utf-8")

        real_lock = manager.interprocess_lock

        @contextmanager
        def state_busy(path, timeout=10.0):
            if Path(path) == manager.STATE_IO_LOCK:
                raise TimeoutError("busy")
            with real_lock(path, timeout=timeout):
                yield

        with mock.patch.object(manager, "interprocess_lock", state_busy):
            result = manager.manager_state_health()
        self.assertFalse(result["healthy"])
        self.assertEqual(result["status"], "busy")
        self.assertIn("SERVICE_MANAGER_STATE_BUSY", result["error"])
        self.assertEqual(manager.STATE_FILE.read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
