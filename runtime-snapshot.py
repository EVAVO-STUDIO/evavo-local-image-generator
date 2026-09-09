#!/usr/bin/env python3
"""Capture reproducible local ComfyUI/runtime/model evidence for a quality run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
DEFAULT_CACHE = ROOT / ".evavo" / "model-hash-cache.json"


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)


def _default_comfy_root(endpoint: str) -> Path:
    env = os.getenv("EVAVO_COMFYUI_DIR") or os.getenv("COMFYUI_DIR")
    if env:
        return Path(env).expanduser()
    parsed = urlparse(endpoint)
    port = parsed.port
    return Path(r"C:\AI\ComfyUI-next" if port == 8189 else r"C:\AI\ComfyUI")


def _loopback_http(endpoint: str) -> bool:
    try:
        parsed = urlparse(endpoint)
    except ValueError:
        return False
    return (
        parsed.scheme == "http"
        and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
    )


def _http_json(url: str, timeout: float = 5.0) -> Dict[str, Any]:
    request = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"HTTP JSON request failed for {url}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"HTTP JSON response is not an object: {url}")
    return payload


def _run(argv: list[str], *, cwd: Path | None = None, timeout: float = 20.0) -> Dict[str, Any]:
    try:
        result = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "argv": argv, "error": str(exc)}
    return {
        "ok": result.returncode == 0,
        "argv": argv,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def _git_sha(path: Path) -> str | None:
    git = shutil.which("git")
    if not git or not path.exists():
        return None
    result = _run([git, "-C", str(path), "rev-parse", "HEAD"], timeout=10.0)
    if not result["ok"]:
        return None
    value = str(result["stdout"]).strip()
    return value if len(value) == 40 else None


def _find_python(comfy_root: Path) -> Path | None:
    candidates = (
        comfy_root / ".venv" / "Scripts" / "python.exe",
        comfy_root / "venv" / "Scripts" / "python.exe",
        comfy_root / "python_embeded" / "python.exe",
        comfy_root / "python_embedded" / "python.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    executable = shutil.which("python.exe") or shutil.which("python")
    return Path(executable) if executable else None


def _python_runtime(python: Path | None) -> Dict[str, Any]:
    if python is None:
        return {"ok": False, "error": "Python runtime not found"}
    code = r'''
import json, platform, sys
payload = {
    "python_executable": sys.executable,
    "python_version": platform.python_version(),
    "python_implementation": platform.python_implementation(),
}
try:
    import torch
    payload.update({
        "torch_version": getattr(torch, "__version__", None),
        "torch_cuda_build": getattr(getattr(torch, "version", None), "cuda", None),
        "cuda_available": bool(torch.cuda.is_available()),
        "device_count": int(torch.cuda.device_count()) if torch.cuda.is_available() else 0,
        "device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() and torch.cuda.device_count() else None,
        "device_capability": list(torch.cuda.get_device_capability(0)) if torch.cuda.is_available() and torch.cuda.device_count() else None,
    })
except Exception as exc:
    payload["torch_error"] = str(exc)
print(json.dumps(payload, separators=(",", ":")))
'''.strip()
    result = _run([str(python), "-c", code], timeout=45.0)
    if not result["ok"]:
        return {"ok": False, "python": str(python), "error": result.get("stderr") or result.get("error")}
    try:
        payload = json.loads(result["stdout"])
    except json.JSONDecodeError as exc:
        return {"ok": False, "python": str(python), "error": f"invalid runtime JSON: {exc}"}
    return {"ok": True, **payload}


def _nvidia_snapshot() -> Dict[str, Any]:
    executable = shutil.which("nvidia-smi.exe") or shutil.which("nvidia-smi")
    if not executable:
        return {"ok": False, "error": "nvidia-smi not found"}
    query = "name,driver_version,memory.total"
    result = _run([executable, f"--query-gpu={query}", "--format=csv,noheader,nounits"], timeout=15.0)
    if not result["ok"]:
        return {"ok": False, "error": result.get("stderr") or "nvidia-smi failed"}
    gpus = []
    for line in str(result["stdout"]).splitlines():
        parts = [item.strip() for item in line.split(",")]
        if len(parts) >= 3:
            try:
                memory_mib = int(parts[2])
            except ValueError:
                memory_mib = None
            gpus.append({"name": parts[0], "driver_version": parts[1], "memory_total_mib": memory_mib})
    return {"ok": bool(gpus), "gpus": gpus}


def _load_hash_cache(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _sha256_cached(path: Path, cache_path: Path) -> Dict[str, Any]:
    resolved = path.resolve(strict=True)
    stat = resolved.stat()
    key = str(resolved)
    cache = _load_hash_cache(cache_path)
    cached = cache.get(key)
    if (
        isinstance(cached, dict)
        and cached.get("size") == stat.st_size
        and cached.get("mtime_ns") == stat.st_mtime_ns
        and isinstance(cached.get("sha256"), str)
        and len(cached["sha256"]) == 64
    ):
        return {"path": key, "size": stat.st_size, "sha256": cached["sha256"], "hash_cache_hit": True}

    digest = hashlib.sha256()
    with resolved.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    cache[key] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "sha256": value}
    _write_json(cache_path, cache)
    return {"path": key, "size": stat.st_size, "sha256": value, "hash_cache_hit": False}


def _search_roots(comfy_root: Path, kind: str, extra_roots: Iterable[Path]) -> list[Path]:
    roots = [comfy_root / "models" / kind]
    roots.extend(extra_roots)
    unique: list[Path] = []
    seen = set()
    for root in roots:
        value = str(root.expanduser().resolve()) if root.exists() else str(root.expanduser().absolute())
        key = value.lower() if os.name == "nt" else value
        if key not in seen:
            unique.append(Path(value))
            seen.add(key)
    return unique


def _locate_named_model(name: str, roots: Iterable[Path]) -> Path | None:
    normalized = name.replace("\\", "/").strip("/")
    basename = Path(normalized).name
    for root in roots:
        direct = root / Path(normalized)
        if direct.is_file():
            return direct.resolve()
    for root in roots:
        if not root.is_dir():
            continue
        try:
            for candidate in root.rglob(basename):
                if candidate.is_file():
                    return candidate.resolve()
        except OSError:
            continue
    return None


def _manifest_recipe(manifest: Dict[str, Any]) -> Dict[str, Any]:
    results = manifest.get("results")
    completed = [item for item in results if isinstance(item, dict) and item.get("status") == "completed"] if isinstance(results, list) else []
    checkpoint = manifest.get("checkpoint")
    if not checkpoint:
        for item in completed:
            if item.get("checkpoint"):
                checkpoint = item["checkpoint"]
                break
    loras: Dict[str, Dict[str, Any]] = {}
    for item in completed:
        lora = item.get("lora")
        if isinstance(lora, dict) and lora.get("name"):
            loras[str(lora["name"])] = lora
    if manifest.get("lora_name") and str(manifest["lora_name"]) not in loras:
        loras[str(manifest["lora_name"])] = {"name": manifest["lora_name"]}
    return {"checkpoint": checkpoint, "loras": list(loras.values())}


def _custom_nodes(comfy_root: Path) -> list[Dict[str, Any]]:
    root = comfy_root / "custom_nodes"
    if not root.is_dir():
        return []
    nodes = []
    for child in sorted(root.iterdir(), key=lambda value: value.name.lower()):
        if not child.is_dir() or child.name.startswith(".") or child.name == "__pycache__":
            continue
        nodes.append({"name": child.name, "git_sha": _git_sha(child)})
    return nodes


def capture_snapshot(
    *,
    endpoint: str,
    comfy_root: Path,
    manifest: Dict[str, Any] | None,
    checkpoint: str | None,
    extra_model_roots: list[Path],
    hash_cache: Path,
) -> Dict[str, Any]:
    recipe = _manifest_recipe(manifest or {})
    checkpoint_name = checkpoint or recipe.get("checkpoint") or os.getenv("EVAVO_COMFYUI_CHECKPOINT")
    python = _find_python(comfy_root)

    evidence: Dict[str, Any] = {
        "schema_version": 1,
        "captured_at": datetime.now().astimezone().isoformat(),
        "endpoint": endpoint,
        "comfy_root": str(comfy_root.expanduser().resolve()) if comfy_root.exists() else str(comfy_root),
        "host_python": platform.python_version(),
        "generator_repo_git_sha": _git_sha(ROOT),
        "comfyui_git_sha": _git_sha(comfy_root),
        "python_runtime": _python_runtime(python),
        "nvidia": _nvidia_snapshot(),
        "custom_nodes": _custom_nodes(comfy_root),
        "checkpoint": {"name": checkpoint_name},
        "loras": [],
        "errors": [],
    }

    if _loopback_http(endpoint):
        try:
            evidence["system_stats"] = _http_json(endpoint.rstrip("/") + "/system_stats")
        except RuntimeError as exc:
            evidence["errors"].append(str(exc))
    else:
        evidence["errors"].append("runtime snapshot only permits loopback HTTP ComfyUI endpoints")

    checkpoint_roots = _search_roots(comfy_root, "checkpoints", extra_model_roots)
    if checkpoint_name:
        path = _locate_named_model(str(checkpoint_name), checkpoint_roots)
        if path is None:
            evidence["errors"].append(f"checkpoint bytes not found locally: {checkpoint_name}")
        else:
            evidence["checkpoint"].update(_sha256_cached(path, hash_cache))
    else:
        evidence["errors"].append("checkpoint name could not be resolved")

    lora_roots = _search_roots(comfy_root, "loras", extra_model_roots)
    for lora in recipe.get("loras", []):
        name = str(lora.get("name", ""))
        item = dict(lora)
        path = _locate_named_model(name, lora_roots) if name else None
        if path is None:
            item["hash_error"] = f"LoRA bytes not found locally: {name}"
            evidence["errors"].append(item["hash_error"])
        else:
            item.update(_sha256_cached(path, hash_cache))
        evidence["loras"].append(item)

    evidence["complete"] = bool(
        evidence["python_runtime"].get("ok")
        and evidence["checkpoint"].get("sha256")
        and not evidence["errors"]
    )
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture ComfyUI/Python/GPU/model checksums for an EVAVO quality run")
    parser.add_argument("--manifest", default=None, help="Benchmark manifest used to resolve checkpoint/LoRA recipe")
    parser.add_argument("--endpoint", default=None)
    parser.add_argument("--comfy-root", default=None)
    parser.add_argument("--checkpoint", default=None)
    parser.add_argument("--model-root", action="append", default=[], help="Additional checkpoint/LoRA search root; may be repeated")
    parser.add_argument("--hash-cache", default=str(DEFAULT_CACHE))
    parser.add_argument("--output", default=None)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).expanduser().resolve() if args.manifest else None
    try:
        manifest = _read_json(manifest_path) if manifest_path else None
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    endpoint = args.endpoint or (manifest.get("endpoint") if manifest else None) or os.getenv("COMFYUI_ENDPOINT") or "http://127.0.0.1:8188"
    comfy_root = Path(args.comfy_root).expanduser() if args.comfy_root else _default_comfy_root(endpoint)
    extra_roots = [Path(value).expanduser() for value in args.model_root]
    env_roots = os.getenv("EVAVO_MODEL_ROOTS")
    if env_roots:
        extra_roots.extend(Path(value).expanduser() for value in env_roots.split(";") if value.strip())

    try:
        snapshot = capture_snapshot(
            endpoint=endpoint,
            comfy_root=comfy_root,
            manifest=manifest,
            checkpoint=args.checkpoint,
            extra_model_roots=extra_roots,
            hash_cache=Path(args.hash_cache).expanduser().resolve(),
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    output = Path(args.output).expanduser().resolve() if args.output else (
        manifest_path.parent / "runtime-evidence.json" if manifest_path else ROOT / ".evavo" / "quality-results" / "runtime-evidence.json"
    )
    _write_json(output, snapshot)
    print(json.dumps(snapshot, indent=2, ensure_ascii=False))
    print(f"Runtime evidence: {output}")
    if args.require_complete and not snapshot["complete"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
