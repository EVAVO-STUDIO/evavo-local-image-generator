from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from evavo_local_image_generator import comfyui_repair as repair


def _must_not_run(*args, **kwargs):
    raise AssertionError("subprocess must not run")


def _isolate_evidence(monkeypatch, tmp_path: Path) -> tuple[Path, Path]:
    diagnostic = tmp_path / "comfy-startup-output.txt"
    failure = tmp_path / "native-comfyui-last-failure.json"
    monkeypatch.setattr(repair, "DIAGNOSTIC_OUTPUT_FILE", diagnostic)
    monkeypatch.setattr(repair, "LAST_FAILURE_FILE", failure)
    return diagnostic, failure


def test_no_repair_evidence_does_not_mutate(monkeypatch, tmp_path: Path) -> None:
    _isolate_evidence(monkeypatch, tmp_path)
    monkeypatch.setattr(repair, "load_last_failure", lambda: {})
    monkeypatch.setattr(repair.subprocess, "run", _must_not_run)

    result = repair.repair_backend_dependencies()

    assert result["ok"] is False
    assert result["error_code"] == "NO_REPAIR_EVIDENCE"
    assert result["repair_performed"] is False


def test_custom_node_dependency_refuses_core_requirements_mutation(monkeypatch, tmp_path: Path) -> None:
    _isolate_evidence(monkeypatch, tmp_path)
    monkeypatch.setattr(
        repair,
        "load_last_failure",
        lambda: {
            "category": "custom_node_dependency",
            "missing_modules": ["some_custom_requirement"],
        },
    )
    monkeypatch.setattr(repair.subprocess, "run", _must_not_run)

    result = repair.repair_backend_dependencies()

    assert result["ok"] is False
    assert result["error_code"] == "CUSTOM_NODE_DEPENDENCY"
    assert result["missing_modules"] == ["some_custom_requirement"]
    assert result["repair_performed"] is False


def test_missing_core_dependency_uses_structured_failure_module(monkeypatch, tmp_path: Path) -> None:
    _isolate_evidence(monkeypatch, tmp_path)
    script = tmp_path / "repair-comfyui-dependencies.py"
    script.write_text("# test repair entrypoint\n", encoding="utf-8")
    monkeypatch.setattr(repair, "ROOT", tmp_path)
    monkeypatch.setattr(repair, "REPAIR_SCRIPT", script)
    monkeypatch.setattr(
        repair,
        "load_last_failure",
        lambda: {
            "category": "missing_dependency",
            "missing_modules": ["comfy_aimdo"],
        },
    )

    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = list(command)
        captured["kwargs"] = kwargs
        return type(
            "Completed",
            (),
            {
                "returncode": 0,
                "stdout": json.dumps({"ok": True, "status": "repaired", "repair_performed": True}),
                "stderr": "",
            },
        )()

    monkeypatch.setattr(repair.subprocess, "run", fake_run)

    result = repair.repair_backend_dependencies(timeout_seconds=120)

    command = captured["command"]
    assert isinstance(command, list)
    assert command[1] == str(script)
    assert command[command.index("--module") + 1] == "comfy_aimdo"
    assert command[command.index("--timeout") + 1] == "120"
    assert "--force-sync" not in command
    assert captured["kwargs"]["shell"] is False
    assert result["ok"] is True
    assert result["status"] == "repaired"
    assert result["source_failure_category"] == "missing_dependency"
    assert result["agent_safe"] is True
    assert result["used_checkout_requirements"] is True
    assert result["used_shell"] is False


def test_newer_bounded_diagnostic_log_admits_repair(monkeypatch, tmp_path: Path) -> None:
    diagnostic, failure = _isolate_evidence(monkeypatch, tmp_path)
    failure.write_text(
        json.dumps({"category": "startup_exception", "missing_modules": []}),
        encoding="utf-8",
    )
    old = 1_700_000_000
    os.utime(failure, (old, old))
    diagnostic.write_text(
        "Traceback (most recent call last):\n"
        "  File 'C:\\AI\\ComfyUI\\main.py', line 69, in <module>\n"
        "ModuleNotFoundError: No module named 'comfy_aimdo'\n",
        encoding="utf-8",
    )
    os.utime(diagnostic, (old + 10, old + 10))
    monkeypatch.setattr(repair, "load_last_failure", lambda: {"category": "startup_exception", "missing_modules": []})

    script = tmp_path / "repair-comfyui-dependencies.py"
    script.touch()
    monkeypatch.setattr(repair, "ROOT", tmp_path)
    monkeypatch.setattr(repair, "REPAIR_SCRIPT", script)

    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = list(command)
        return type(
            "Completed",
            (),
            {
                "returncode": 0,
                "stdout": json.dumps({"ok": True, "status": "repaired", "repair_performed": True}),
                "stderr": "",
            },
        )()

    monkeypatch.setattr(repair.subprocess, "run", fake_run)

    result = repair.repair_backend_dependencies(timeout_seconds=60)

    command = captured["command"]
    assert isinstance(command, list)
    assert command[command.index("--module") + 1] == "comfy_aimdo"
    assert result["source_failure_category"] == "missing_dependency"
    assert result["evidence_source"] == "bounded_diagnostic_log"
    assert result["evidence_path"] == str(diagnostic)
    assert result["ok"] is True


def test_newer_custom_node_diagnostic_still_refuses_core_sync(monkeypatch, tmp_path: Path) -> None:
    diagnostic, failure = _isolate_evidence(monkeypatch, tmp_path)
    failure.write_text(json.dumps({"category": "missing_dependency", "missing_modules": ["old_module"]}), encoding="utf-8")
    old = 1_700_000_000
    os.utime(failure, (old, old))
    diagnostic.write_text(
        "Loading custom_nodes\\example\\prestartup_script.py\n"
        "ModuleNotFoundError: No module named 'custom_only_dependency'\n",
        encoding="utf-8",
    )
    os.utime(diagnostic, (old + 10, old + 10))
    monkeypatch.setattr(repair, "load_last_failure", lambda: {"category": "missing_dependency", "missing_modules": ["old_module"]})
    monkeypatch.setattr(repair.subprocess, "run", _must_not_run)

    result = repair.repair_backend_dependencies()

    assert result["ok"] is False
    assert result["error_code"] == "CUSTOM_NODE_DEPENDENCY"
    assert result["evidence_source"] == "bounded_diagnostic_log"
    assert result["repair_performed"] is False


def test_force_sync_is_explicit_and_uses_default_core_probe(monkeypatch, tmp_path: Path) -> None:
    _isolate_evidence(monkeypatch, tmp_path)
    script = tmp_path / "repair-comfyui-dependencies.py"
    script.touch()
    monkeypatch.setattr(repair, "ROOT", tmp_path)
    monkeypatch.setattr(repair, "REPAIR_SCRIPT", script)
    monkeypatch.setattr(repair, "load_last_failure", lambda: {})

    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = list(command)
        return type(
            "Completed",
            (),
            {
                "returncode": 0,
                "stdout": json.dumps({"ok": True, "status": "already_healthy", "repair_performed": True}),
                "stderr": "",
            },
        )()

    monkeypatch.setattr(repair.subprocess, "run", fake_run)

    result = repair.repair_backend_dependencies(force_sync=True)

    command = captured["command"]
    assert isinstance(command, list)
    assert "--force-sync" in command
    assert command[command.index("--module") + 1] == repair.DEFAULT_CORE_MODULE
    assert result["ok"] is True


def test_repair_timeout_validation_is_bounded() -> None:
    with pytest.raises(ValueError):
        repair.build_repair_command(module="comfy_aimdo", timeout_seconds=0)
    with pytest.raises(ValueError):
        repair.build_repair_command(module="comfy_aimdo", timeout_seconds=3601)
    with pytest.raises(ValueError):
        repair.build_repair_command(module="bad module name", timeout_seconds=60)
