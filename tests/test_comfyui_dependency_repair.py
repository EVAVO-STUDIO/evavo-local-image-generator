from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


SCRIPT = Path(__file__).resolve().parents[1] / "repair-comfyui-dependencies.py"
SPEC = importlib.util.spec_from_file_location("repair_comfyui_dependencies", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
repair = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(repair)


def test_select_python_prefers_parent_portable_runtime(tmp_path: Path) -> None:
    comfy_home = tmp_path / "AI" / "ComfyUI"
    comfy_home.mkdir(parents=True)
    portable = tmp_path / "AI" / "python_embeded" / "python.exe"
    portable.parent.mkdir(parents=True)
    portable.touch()

    selected = repair._select_python(comfy_home)

    assert selected == portable.resolve()
    assert repair._is_portable_python(selected)


def test_explicit_python_wins_over_discovery(tmp_path: Path) -> None:
    comfy_home = tmp_path / "ComfyUI"
    comfy_home.mkdir()
    explicit = tmp_path / "custom-python.exe"
    explicit.touch()
    venv_python = comfy_home / ".venv" / "Scripts" / "python.exe"
    venv_python.parent.mkdir(parents=True)
    venv_python.touch()

    selected = repair._select_python(comfy_home, str(explicit))

    assert selected == explicit.resolve()


def test_portable_pip_sync_uses_isolated_local_requirements(tmp_path: Path) -> None:
    python_exe = tmp_path / "python_embeded" / "python.exe"
    requirements = tmp_path / "ComfyUI" / "requirements.txt"

    command = repair._pip_install_command(python_exe, requirements)

    assert command[:4] == [str(python_exe), "-s", "-m", "pip"]
    assert command[-2:] == ["-r", str(requirements)]
    assert "--upgrade" not in command


def test_source_python_does_not_get_portable_isolation(tmp_path: Path) -> None:
    python_exe = tmp_path / ".venv" / "Scripts" / "python.exe"
    requirements = tmp_path / "ComfyUI" / "requirements.txt"

    command = repair._pip_install_command(python_exe, requirements)

    assert command[:3] == [str(python_exe), "-m", "pip"]
    assert "-s" not in command


def test_healthy_dependency_path_does_not_mutate(monkeypatch, tmp_path: Path) -> None:
    comfy_home = tmp_path / "ComfyUI"
    comfy_home.mkdir()
    (comfy_home / "main.py").write_text("", encoding="utf-8")
    (comfy_home / "requirements.txt").write_text("comfy-aimdo==0.5.3\n", encoding="utf-8")
    python_exe = tmp_path / "python.exe"
    python_exe.touch()

    commands: list[list[str]] = []

    def fake_run(command, *, cwd, timeout):
        command = list(command)
        commands.append(command)
        if "pip" in command and "check" in command:
            return {"command": command, "returncode": 0, "stdout": "No broken requirements found.\n", "stderr": "", "duration_seconds": 0.01, "timed_out": False}
        if "pip" in command and "--version" in command:
            return {"command": command, "returncode": 0, "stdout": "pip 25.0\n", "stderr": "", "duration_seconds": 0.01, "timed_out": False}
        return {"command": command, "returncode": 0, "stdout": "{\"ok\": true}\n", "stderr": "", "duration_seconds": 0.01, "timed_out": False}

    monkeypatch.setattr(repair, "_run", fake_run)

    exit_code, payload = repair.repair_dependencies(
        comfy_home=str(comfy_home),
        python_exe=str(python_exe),
    )

    assert exit_code == 0
    assert payload["status"] == "already_healthy"
    assert payload["repair_performed"] is False
    assert not any("install" in command for command in commands)


def test_missing_module_syncs_checkout_requirements_then_verifies(monkeypatch, tmp_path: Path) -> None:
    comfy_home = tmp_path / "ComfyUI"
    comfy_home.mkdir()
    requirements = comfy_home / "requirements.txt"
    (comfy_home / "main.py").write_text("", encoding="utf-8")
    requirements.write_text("comfy-aimdo==0.5.3\n", encoding="utf-8")
    python_exe = tmp_path / "python.exe"
    python_exe.touch()

    commands: list[list[str]] = []
    probe_count = 0

    def fake_run(command, *, cwd, timeout):
        nonlocal probe_count
        command = list(command)
        commands.append(command)
        if "-c" in command:
            probe_count += 1
            return {
                "command": command,
                "returncode": 1 if probe_count == 1 else 0,
                "stdout": "" if probe_count == 1 else "{\"ok\": true}\n",
                "stderr": "ModuleNotFoundError: No module named 'comfy_aimdo'" if probe_count == 1 else "",
                "duration_seconds": 0.01,
                "timed_out": False,
            }
        return {"command": command, "returncode": 0, "stdout": "ok\n", "stderr": "", "duration_seconds": 0.01, "timed_out": False}

    monkeypatch.setattr(repair, "_run", fake_run)

    exit_code, payload = repair.repair_dependencies(
        comfy_home=str(comfy_home),
        python_exe=str(python_exe),
    )

    assert exit_code == 0
    assert payload["status"] == "repaired"
    assert payload["repair_performed"] is True
    install_commands = [command for command in commands if "install" in command]
    assert len(install_commands) == 1
    assert install_commands[0][-2:] == ["-r", str(requirements)]
    assert "--upgrade" not in install_commands[0]
