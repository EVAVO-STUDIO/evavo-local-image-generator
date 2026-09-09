from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

try:
    import evavo_local_image_generator.comfyui_runtime  # noqa: F401
except ModuleNotFoundError:  # isolated contract-test fallback
    package = types.ModuleType("evavo_local_image_generator")
    runtime = types.ModuleType("evavo_local_image_generator.comfyui_runtime")
    runtime.ensure_comfyui = lambda *args, **kwargs: {"ok": True}
    runtime.native_health = lambda *args, **kwargs: {"ok": True}
    runtime.stop_managed_comfyui = lambda: {"stopped": False}
    sys.modules["evavo_local_image_generator"] = package
    sys.modules["evavo_local_image_generator.comfyui_runtime"] = runtime

MANAGER_PATH = Path(__file__).resolve().parents[1] / "EVAVO-SERVICE-MANAGER.py"
if not MANAGER_PATH.is_file():
    MANAGER_PATH = Path(__file__).resolve().with_name("EVAVO-SERVICE-MANAGER.py")
spec = importlib.util.spec_from_file_location("evavo_gateway_service_manager_test", MANAGER_PATH)
manager = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(manager)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def fake_3d_repo(repo: Path) -> None:
    package = repo / "evavo_3d_studio"
    package.mkdir(parents=True)
    (repo / "pyproject.toml").write_text('[project]\nname="evavo-3d-studio"\n', encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "agent_worker.py").write_text(
        '''import argparse, json, os\nfrom http.server import BaseHTTPRequestHandler, ThreadingHTTPServer\nclass H(BaseHTTPRequestHandler):\n    def send_json(self, code, value):\n        data=(json.dumps(value)+"\\n").encode(); self.send_response(code); self.send_header("content-length",str(len(data))); self.end_headers(); self.wfile.write(data)\n    def do_GET(self):\n        if self.path == "/api/v1/health":\n            self.send_json(200,{"ok":True,"service":"evavo-3d-agent-worker","executionEnabled":os.environ.get("EVAVO_3D_AGENT_EXECUTION_ENABLED")=="1"}); return\n        if self.path.startswith("/api/v1/jobs/"):\n            if self.headers.get("authorization") != "Bearer "+os.environ.get("EVAVO_3D_AGENT_EXECUTION_TOKEN",""):\n                self.send_json(403,{"ok":False}); return\n            self.send_json(404,{"ok":False,"error":"missing"}); return\n        self.send_json(404,{"ok":False})\n    def log_message(self,*args): return\np=argparse.ArgumentParser(); sub=p.add_subparsers(dest="command",required=True); s=sub.add_parser("serve"); s.add_argument("--host"); s.add_argument("--port",type=int); s.add_argument("--workspace-root"); a=p.parse_args()\nif len(os.environ.get("EVAVO_3D_AGENT_EXECUTION_TOKEN","")) < 32: raise SystemExit(4)\nThreadingHTTPServer((a.host,a.port),H).serve_forever()\n''',
        encoding="utf-8",
    )


class ProviderServiceManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patch = mock.patch.dict(os.environ, {}, clear=False)
        self.env_patch.start()
        for key in (
            "EVAVO_AUDIO_PROVIDER_ARGV", "EVAVO_AUDIO_STUDIO_DIR", "EVAVO_AUDIO_PROVIDER_TIMEOUT", "EVAVO_AUDIO_PYTHON",
            "EVAVO_VIDEO_PROVIDER_ARGV", "EVAVO_VIDEO_STUDIO_DIR", "EVAVO_VIDEO_PROVIDER_TIMEOUT", "EVAVO_VIDEO_PYTHON",
            "EVAVO_WAN21_MODEL_DIR", "EVAVO_WAN21_MODEL_MANIFEST_SHA256",
            "EVAVO_3D_STUDIO_DIR", "EVAVO_3D_AGENT_EXECUTION_TOKEN", "EVAVO_3D_AGENT_EXECUTION_ENABLED",
            "EVAVO_3D_AGENT_WORKSPACE_ROOT", "EVAVO_3D_PYTHON", "EVAVO_GATEWAY_MANAGE_3D", "EVAVO_3D_PROVIDER_TIMEOUT",
        ):
            os.environ.pop(key, None)
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name) / "Gitrepos"
        gateway = base / "evavo-local-image-generator"
        gateway.mkdir(parents=True)
        self.original_3d_url = manager.THREE_D_URL
        manager.ROOT = gateway.resolve()
        manager.STATE_DIR = (gateway / ".evavo" / "gateway").resolve()
        manager.STATE_FILE = manager.STATE_DIR / "service-manager.json"
        manager.TOKEN_FILE = manager.STATE_DIR / "3d-worker.token"
        manager.LOG_DIR = manager.STATE_DIR / "logs"
        manager.GATEWAY_SCRIPT = manager.ROOT / "EVAVO-GATEWAY.py"

    def tearDown(self) -> None:
        manager.THREE_D_URL = self.original_3d_url
        self.temp.cleanup()
        self.env_patch.stop()

    def test_local_endpoint_validation(self) -> None:
        self.assertEqual(manager.endpoint_host_port("http://127.0.0.1:4314", expected_default_port=4314), ("127.0.0.1", 4314))
        for endpoint in ("https://127.0.0.1:4314", "http://0.0.0.0:4314", "http://example.com:4314", "http://127.0.0.1:4314/path"):
            with self.subTest(endpoint=endpoint), self.assertRaises(RuntimeError):
                manager.endpoint_host_port(endpoint, expected_default_port=4314)

    def test_audio_sibling_is_configured_as_json_argv(self) -> None:
        repo = manager.ROOT.parent / "evavo-audio-studio"
        repo.mkdir()
        worker = repo / "worker_provider.py"
        worker.write_text("# test worker\n", encoding="utf-8")
        result = manager.configure_audio_provider()
        self.assertTrue(result["configured"])
        argv = json.loads(os.environ["EVAVO_AUDIO_PROVIDER_ARGV"])
        self.assertEqual(Path(argv[1]), worker)
        self.assertEqual(argv[-6:], ["--request-json", "{request_json}", "--output-dir", "{output_dir}", "--task-id", "{task_id}"])
        self.assertEqual(os.environ["EVAVO_AUDIO_PROVIDER_TIMEOUT"], "7200")

    def test_provider_fingerprint_tracks_token_rotation_without_persisting_plaintext(self) -> None:
        first_secret = "sensitive-token-a-" + "x" * 40
        second_secret = "sensitive-token-b-" + "y" * 40
        with mock.patch.dict(
            os.environ,
            {"EVAVO_3D_AGENT_EXECUTION_TOKEN": first_secret, "EVAVO_AUDIO_PROVIDER_ARGV": '["python","worker.py"]'},
            clear=False,
        ):
            first = manager.provider_configuration_fingerprint()
            os.environ["EVAVO_3D_AGENT_EXECUTION_TOKEN"] = second_secret
            second = manager.provider_configuration_fingerprint()
        self.assertRegex(first, r"^[0-9a-f]{64}$")
        self.assertRegex(second, r"^[0-9a-f]{64}$")
        self.assertNotEqual(first, second)
        self.assertNotIn(first_secret, first)
        self.assertNotIn(second_secret, second)

        state = {"gateway": {"managed": True, "pid": 1234, "provider_fingerprint": second}}
        manager.save_state(state)
        persisted = manager.STATE_FILE.read_text(encoding="utf-8")
        self.assertIn(second, persisted)
        self.assertNotIn(first_secret, persisted)
        self.assertNotIn(second_secret, persisted)
        self.assertNotIn("3d_token", persisted.lower())

    def test_managed_gateway_restarts_when_provider_fingerprint_changes(self) -> None:
        manager.GATEWAY_SCRIPT.write_text("# gateway fixture\n", encoding="utf-8")
        state = {"gateway": {"managed": True, "pid": 1234, "provider_fingerprint": "old"}}
        fake_process = types.SimpleNamespace(pid=5678, poll=lambda: None)
        with (
            mock.patch.object(manager, "provider_configuration_fingerprint", return_value="new"),
            mock.patch.object(manager, "gateway_health", return_value={"gateway_alive": True, "healthy": True}),
            mock.patch.object(manager, "pid_matches", return_value=True),
            mock.patch.object(manager, "terminate_pid") as terminate,
            mock.patch.object(manager, "wait_for_port_close") as wait_close,
            mock.patch.object(manager, "port_open", return_value=False),
            mock.patch.object(manager, "spawn_gateway", return_value=fake_process),
            mock.patch.object(manager, "wait_for"),
        ):
            result = manager.ensure_gateway_service(state)
        terminate.assert_called_once_with(1234)
        wait_close.assert_called_once()
        self.assertEqual(result["status"], "started")
        self.assertTrue(result["provider_configuration_applied"])
        self.assertEqual(state["gateway"]["provider_fingerprint"], "new")

    def test_external_gateway_is_never_restarted_for_provider_config(self) -> None:
        state: dict[str, object] = {}
        with (
            mock.patch.object(manager, "provider_configuration_fingerprint", return_value="new"),
            mock.patch.object(manager, "gateway_health", return_value={"gateway_alive": True, "healthy": True}),
            mock.patch.object(manager, "terminate_pid") as terminate,
        ):
            result = manager.ensure_gateway_service(state)
        terminate.assert_not_called()
        self.assertEqual(result["status"], "already_running_external")
        self.assertFalse(result["provider_configuration_applied"])

    def test_full_health_surfaces_gateway_provider_projection_without_affecting_core_status(self) -> None:
        providers = {"image": {"ready": True}, "video": {"ready": False}, "audio": {"ready": False}, "3d": {"ready": False}}
        with (
            mock.patch.object(manager, "comfyui_health", return_value={"healthy": True}),
            mock.patch.object(manager, "gateway_health", return_value={"healthy": True, "gateway_alive": True}),
            mock.patch.object(manager, "gateway_services", return_value=providers),
            mock.patch.object(manager, "manager_state_health", return_value={"healthy": True, "status": "missing"}),
            mock.patch.object(manager, "audio_provider_status", return_value={"configured": False}),
            mock.patch.object(manager, "three_d_health", return_value={"healthy": False}),
        ):
            health = manager.full_health()
        self.assertEqual(health["status"], "healthy")
        self.assertTrue(health["core_ready"])
        self.assertEqual(health["providers"], providers)

    def test_corrupt_manager_state_degrades_health_and_is_not_rewritten(self) -> None:
        manager.STATE_DIR.mkdir(parents=True, exist_ok=True)
        corrupt = "{not valid json\n"
        manager.STATE_FILE.write_text(corrupt, encoding="utf-8")
        with (
            mock.patch.object(manager, "comfyui_health", return_value={"healthy": True}),
            mock.patch.object(manager, "gateway_health", return_value={"healthy": True, "gateway_alive": True}),
            mock.patch.object(manager, "gateway_services", return_value={"image": {"ready": True}}),
            mock.patch.object(manager, "audio_provider_status", return_value={"configured": False}),
            mock.patch.object(manager, "three_d_health", return_value={"healthy": False}),
        ):
            health = manager.full_health()
        self.assertTrue(health["core_ready"])
        self.assertEqual(health["status"], "degraded")
        self.assertFalse(health["manager_state"]["healthy"])
        self.assertEqual(health["manager_state"]["status"], "corrupt")
        self.assertIn("SERVICE_MANAGER_STATE_CORRUPT", health["manager_state"]["error"])
        self.assertEqual(manager.STATE_FILE.read_text(encoding="utf-8"), corrupt)

    def test_corrupt_manager_state_blocks_stop_before_any_process_mutation(self) -> None:
        manager.STATE_DIR.mkdir(parents=True, exist_ok=True)
        manager.STATE_FILE.write_text("{broken", encoding="utf-8")
        with (
            mock.patch.object(manager, "terminate_pid") as terminate,
            mock.patch.object(manager, "stop_managed_comfyui") as stop_native,
        ):
            with self.assertRaises(RuntimeError) as context:
                manager.stop_services()
        self.assertIn("SERVICE_MANAGER_STATE_CORRUPT", str(context.exception))
        terminate.assert_not_called()
        stop_native.assert_not_called()
        self.assertTrue(manager.STATE_FILE.is_file())

    def test_corrupt_manager_state_blocks_start_before_provider_or_backend_mutation(self) -> None:
        manager.STATE_DIR.mkdir(parents=True, exist_ok=True)
        manager.STATE_FILE.write_text("{broken", encoding="utf-8")
        with (
            mock.patch.object(manager, "configure_audio_provider") as configure_audio,
            mock.patch.object(manager, "ensure_3d_worker_service") as ensure_3d,
            mock.patch.object(manager, "ensure_comfyui_service") as ensure_comfy,
            mock.patch.object(manager, "ensure_gateway_service") as ensure_gateway,
        ):
            with self.assertRaises(RuntimeError) as context:
                manager.start_services()
        self.assertIn("SERVICE_MANAGER_STATE_CORRUPT", str(context.exception))
        configure_audio.assert_not_called()
        ensure_3d.assert_not_called()
        ensure_comfy.assert_not_called()
        ensure_gateway.assert_not_called()

    def test_managed_3d_token_is_strong_and_stable(self) -> None:
        token, source = manager.ensure_3d_token(allow_create=True)
        self.assertEqual(source, "generated-managed-state")
        self.assertIsNotNone(token)
        self.assertGreaterEqual(len(token or ""), 32)
        os.environ.pop("EVAVO_3D_AGENT_EXECUTION_TOKEN", None)
        second, source = manager.ensure_3d_token(allow_create=False)
        self.assertEqual(source, "managed-state")
        self.assertEqual(second, token)

    def test_managed_3d_worker_proves_identity_and_token(self) -> None:
        repo = manager.ROOT.parent / "evavo-3d-studio"
        fake_3d_repo(repo)
        port = free_port()
        manager.THREE_D_URL = f"http://127.0.0.1:{port}"
        result = manager.ensure_3d_worker_service({})
        pid = int(result["pid"])
        try:
            self.assertTrue(result["ready"])
            self.assertTrue(manager.three_d_health()["healthy"])
            token = os.environ["EVAVO_3D_AGENT_EXECUTION_TOKEN"]
            self.assertTrue(manager.three_d_token_ready(token))
            self.assertFalse(manager.three_d_token_ready("x" * 48))
            self.assertTrue(manager.pid_matches_tokens(pid, "evavo_3d_studio.agent_worker", "serve"))
        finally:
            if manager.pid_matches_tokens(pid, "evavo_3d_studio.agent_worker", "serve"):
                manager.terminate_pid(pid)
            for _ in range(40):
                if not manager.port_open("127.0.0.1", port):
                    break
                time.sleep(0.05)
        self.assertFalse(manager.port_open("127.0.0.1", port))

    def test_unknown_preexisting_worker_is_not_adopted(self) -> None:
        repo = manager.ROOT.parent / "evavo-3d-studio"
        fake_3d_repo(repo)
        with mock.patch.object(manager, "three_d_health", return_value={"healthy": True}):
            result = manager.ensure_3d_worker_service({})
        self.assertFalse(result["ready"])
        self.assertEqual(result["status"], "already_running_token_unavailable")


if __name__ == "__main__":
    unittest.main()
