#!/usr/bin/env python3
"""Unit tests for one-time custom-workflow preflight in CLI batches."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parent
BATCH_SCRIPT = ROOT / "generate-batch.py"


def load_batch_module():
    spec = importlib.util.spec_from_file_location("evavo_generate_batch", BATCH_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load generate-batch.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def args(**overrides):
    values = {
        "endpoint": "http://127.0.0.1:18198",
        "skip_preflight": False,
        "workflow": "C:/workflows/custom.json",
        "skip_workflow_preflight": False,
        "json": True,
        "project": "batch_test",
        "concurrency": 2,
        "timeout": 30.0,
        "wait": False,
        "wait_timeout": 600.0,
        "output_dir": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeQueuedProcess:
    def __init__(self) -> None:
        self.returncode = 0
        self.killed = False

    async def communicate(self):
        payload = {"ok": True, "status": "queued", "task_id": "prompt-123", "backend_mode": "native-comfyui"}
        return json.dumps(payload).encode("utf-8"), b""

    def kill(self) -> None:
        self.killed = True

    async def wait(self) -> int:
        return self.returncode


class BatchWorkflowPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_batch_module()

    def test_invalid_workflow_aborts_before_batch_generation(self) -> None:
        batch = AsyncMock()
        with (
            patch.object(self.module, "preflight", AsyncMock(return_value={"service": "ComfyUI", "mode": "native-comfyui"})),
            patch.object(self.module, "preflight_custom_workflow", AsyncMock(side_effect=RuntimeError("missing UNET model"))),
            patch.object(self.module, "batch_generate", batch),
            patch("builtins.print"),
        ):
            code = asyncio.run(self.module.async_main(args(), ["one", "two"]))
        self.assertEqual(code, 3)
        batch.assert_not_awaited()

    def test_custom_workflow_rejects_mock_backend_before_queueing(self) -> None:
        workflow_check = AsyncMock()
        batch = AsyncMock()
        with (
            patch.object(self.module, "preflight", AsyncMock(return_value={"service": "EVAVO", "mode": "mock"})),
            patch.object(self.module, "preflight_custom_workflow", workflow_check),
            patch.object(self.module, "batch_generate", batch),
            patch("builtins.print"),
        ):
            code = asyncio.run(self.module.async_main(args(), ["one"]))
        self.assertEqual(code, 3)
        workflow_check.assert_not_awaited()
        batch.assert_not_awaited()

    def test_successful_parent_preflight_marks_batch_as_already_validated(self) -> None:
        batch = AsyncMock(return_value=[{"ok": True, "status": "queued", "task_id": "prompt-1", "prompt": "one", "project_name": "batch_test"}])
        with (
            patch.object(self.module, "preflight", AsyncMock(return_value={"service": "ComfyUI", "mode": "native-comfyui"})),
            patch.object(
                self.module,
                "preflight_custom_workflow",
                AsyncMock(return_value={"ok": True, "workflow_path": "C:/workflows/custom.json", "node_count": 3, "node_classes": ["UNETLoader"]}),
            ),
            patch.object(self.module, "batch_generate", batch),
            patch.object(self.module, "persist_results"),
            patch("builtins.print"),
        ):
            code = asyncio.run(self.module.async_main(args(), ["one"]))
        self.assertEqual(code, 0)
        self.assertTrue(batch.await_args.kwargs["workflow_preflight_already_done"])

    def test_wrapper_skip_flag_is_child_only_after_parent_preflight(self) -> None:
        process_factory = AsyncMock(return_value=FakeQueuedProcess())
        semaphore = asyncio.Semaphore(1)
        with (
            patch.dict(os.environ, {"EVAVO_PREFLIGHT_CUSTOM_WORKFLOW": "1"}, clear=False),
            patch.object(self.module.asyncio, "create_subprocess_exec", process_factory),
        ):
            result = asyncio.run(
                self.module.queue_generation(
                    "one",
                    "batch_test",
                    "http://127.0.0.1:18198",
                    semaphore,
                    30.0,
                    workflow_path="C:/workflows/custom.json",
                    workflow_preflight_already_done=True,
                )
            )
            self.assertEqual(os.environ["EVAVO_PREFLIGHT_CUSTOM_WORKFLOW"], "1")

        self.assertEqual(result["status"], "queued")
        child_env = process_factory.await_args.kwargs["env"]
        self.assertIsInstance(child_env, dict)
        self.assertEqual(child_env["EVAVO_PREFLIGHT_CUSTOM_WORKFLOW"], "0")


if __name__ == "__main__":
    unittest.main(verbosity=2)
