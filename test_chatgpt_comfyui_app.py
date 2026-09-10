"""Static contract tests for the embedded ChatGPT ComfyUI control surface."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SERVER = ROOT / "evavo_local_image_generator" / "mcp_server.py"
APP = ROOT / "evavo_local_image_generator" / "comfyui_app.py"


def test_mcp_app_python_is_valid() -> None:
    ast.parse(SERVER.read_text(encoding="utf-8"))
    ast.parse(APP.read_text(encoding="utf-8"))


def test_open_tool_is_bound_to_versioned_chat_ui() -> None:
    source = SERVER.read_text(encoding="utf-8")
    assert "from mcp.server.apps import Apps" in source
    assert source.count("async def open_comfyui_ui") == 1
    assert "@apps.tool(" in source
    assert 'visibility=["model", "app"]' in source
    assert '"openai/outputTemplate": COMFYUI_APP_URI' in source
    assert '"openai/widgetAccessible": True' in source
    assert "apps.add_html_resource(" in source
    assert 'extensions=[apps]' in source
    assert source.index("@apps.tool(") < source.index('mcp = MCPServer(')


def test_chat_ui_can_start_generate_and_preview_without_embedding_localhost() -> None:
    source = APP.read_text(encoding="utf-8")
    assert 'COMFYUI_APP_URI = "ui://evavo/comfyui/v1.html"' in source
    assert 'call("open_comfyui_ui"' in source
    assert 'call("generate_image"' in source
    assert 'call("read_output_image"' in source
    assert 'call("open_evavo_comfyui_app"' in source
    assert 'method:"tools/call"' in source
    assert "window.openai.callTool" in source
    assert "<iframe" not in source.lower()


def test_loopback_backup_app_has_security_and_generation_guards() -> None:
    source = (ROOT / "evavo_local_image_generator" / "local_app.py").read_text(encoding="utf-8")
    ast.parse(source)
    assert 'DEFAULT_HOST = "127.0.0.1"' in source
    assert "hmac.compare_digest" in source
    assert "SameSite=Strict" in source
    assert "Content-Security-Policy" in source
    assert "MAX_BODY_BYTES" in source
    assert "MAX_PROMPT_CHARS" in source
    assert "_GENERATION_LOCK.acquire(blocking=False)" in source
    assert "_validated_output_image" in source
    assert "shell=False" in source
    assert "ThreadingHTTPServer" in source


def test_mcp_can_open_independent_backup_app() -> None:
    source = SERVER.read_text(encoding="utf-8")
    assert "from .local_app import ensure_local_control_app" in source
    assert "async def open_evavo_comfyui_app" in source
    assert "ensure_local_control_app" in source
