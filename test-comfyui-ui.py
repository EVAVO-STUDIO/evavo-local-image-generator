#!/usr/bin/env python3
"""Safety and agent-contract tests for presenting the local ComfyUI UI."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from evavo_local_image_generator import comfyui_runtime


class ComfyUIUiTests(unittest.TestCase):
    def test_ui_url_accepts_only_plain_loopback_http(self) -> None:
        self.assertEqual(comfyui_runtime.comfyui_ui_url("http://127.0.0.1:8188"), "http://127.0.0.1:8188/")
        self.assertEqual(comfyui_runtime.comfyui_ui_url("http://[::1]:8188/"), "http://[::1]:8188/")
        for invalid in (
            "https://127.0.0.1:8188",
            "http://example.com:8188",
            "http://user:secret@127.0.0.1:8188",
            "http://127.0.0.1:8188/api",
            "http://127.0.0.1:8188/?next=remote",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(RuntimeError):
                comfyui_runtime.comfyui_ui_url(invalid)

    def test_present_dispatches_validated_url_to_default_browser(self) -> None:
        with patch.object(comfyui_runtime.webbrowser, "open_new_tab", return_value=True) as opener:
            result = comfyui_runtime.present_comfyui_ui("http://localhost:8188")
        self.assertTrue(result["opened"])
        self.assertEqual(result["ui_url"], "http://localhost:8188/")
        opener.assert_called_once_with("http://localhost:8188/")

    def test_mcp_tool_ensures_native_backend_before_presenting_ui(self) -> None:
        try:
            from evavo_local_image_generator import mcp_server
        except RuntimeError as exc:
            if "MCP SDK is required" in str(exc):
                self.skipTest("MCP SDK is not installed in this test interpreter")
            raise
        backend = {"status": "already_running", "health": {"mode": "native-comfyui"}}

        async def exercise() -> dict[str, object]:
            with (
                patch.object(mcp_server, "_ensure", new=AsyncMock(return_value=backend)) as ensure,
                patch.object(
                    mcp_server,
                    "present_comfyui_ui",
                    return_value={"opened": True, "ui_url": "http://127.0.0.1:8188/", "method": "default-browser-new-tab"},
                ) as presenter,
            ):
                result = await mcp_server.open_comfyui_ui(auto_start=True, wait_seconds=120)
            ensure.assert_awaited_once_with(auto_start=True, wait_seconds=120)
            presenter.assert_called_once_with("http://127.0.0.1:8188")
            return result

        result = asyncio.run(exercise())
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "ready")
        self.assertIs(result["backend"], backend)

    def test_mcp_tool_preserves_backend_receipt_when_browser_rejects_dispatch(self) -> None:
        try:
            from evavo_local_image_generator import mcp_server
        except RuntimeError as exc:
            if "MCP SDK is required" in str(exc):
                self.skipTest("MCP SDK is not installed in this test interpreter")
            raise
        backend = {"status": "started", "health": {"mode": "native-comfyui"}}

        async def exercise() -> dict[str, object]:
            with (
                patch.object(mcp_server, "_ensure", new=AsyncMock(return_value=backend)),
                patch.object(mcp_server, "present_comfyui_ui", side_effect=RuntimeError("COMFYUI_UI_OPEN_FAILED:no browser")),
            ):
                return await mcp_server.open_comfyui_ui()

        result = asyncio.run(exercise())
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "ready_in_chat")
        self.assertFalse(result["native_ui_opened"])
        self.assertEqual(result["native_ui_warning"], "COMFYUI_UI_OPEN_FAILED:no browser")
        self.assertIs(result["backend"], backend)


    def test_mcp_tool_can_open_independent_loopback_app(self) -> None:
        try:
            from evavo_local_image_generator import mcp_server
        except RuntimeError as exc:
            if "MCP SDK is required" in str(exc):
                self.skipTest("MCP SDK is not installed in this test interpreter")
            raise

        expected = {"ok": True, "status": "ready", "url": "http://127.0.0.1:8770"}

        async def exercise() -> dict[str, object]:
            with patch.object(mcp_server, "ensure_local_control_app", return_value=expected) as opener:
                result = await mcp_server.open_evavo_comfyui_app(port=8770, wait_seconds=30)
            opener.assert_called_once_with(8770, open_browser=True, wait_seconds=30.0)
            return result

        self.assertEqual(asyncio.run(exercise()), expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
