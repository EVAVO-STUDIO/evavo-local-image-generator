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
            "EVAVO_3D_STUDIO_DIR", "EVAVO_3D_AGENT_EXECUTION_TOKEN", "EVAVO_3D_AGENT_EXECUTION_ENABLED",
            "EVAVO_3D_AGENT_WORKSPACE_ROOT", "EVAVO_3D_PYTHON", "EVAVO_GATEWAY_MANAGE_3D",
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
