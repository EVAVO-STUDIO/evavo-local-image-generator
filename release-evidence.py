#!/usr/bin/env python3
"""Create or verify a SHA-256 manifest for an EVAVO local-generation release folder."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

MANIFEST_NAME = "release-manifest.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and path.name != MANIFEST_NAME
        and ".part" not in path.suffixes
    )


def _json_status(path: Path) -> dict[str, Any] | None:
    if path.suffix.lower() != ".json":
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    result: dict[str, Any] = {}
    for key in ("ok", "complete", "passes", "status", "schema_version", "schemaVersion"):
        if key in value:
            result[key] = value[key]
    failures = value.get("failures")
    if isinstance(failures, list):
        result["failure_count"] = len(failures)
    return result or None


def create_manifest(root_value: str | Path) -> dict[str, Any]:
    root = Path(root_value).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"release root is not a directory: {root}")

    entries: list[dict[str, Any]] = []
    total_bytes = 0
    for path in _files(root):
        resolved = path.resolve(strict=True)
        try:
            relative = resolved.relative_to(root).as_posix()
        except ValueError as exc:
            raise ValueError(f"release file escaped root: {resolved}") from exc
        size = resolved.stat().st_size
        total_bytes += size
        entry: dict[str, Any] = {
            "path": relative,
            "bytes": size,
            "sha256": sha256_file(resolved),
        }
        status = _json_status(resolved)
        if status:
            entry["json_status"] = status
        entries.append(entry)

    if not entries:
        raise ValueError("release root contains no evidence files")

    payload = {
        "schema_version": 1,
        "created_at": datetime.now().astimezone().isoformat(),
        "root": str(root),
        "file_count": len(entries),
        "total_bytes": total_bytes,
        "files": entries,
    }
    encoded_entries = json.dumps(entries, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    payload["evidence_set_sha256"] = hashlib.sha256(encoded_entries).hexdigest()

    target = root / MANIFEST_NAME
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, target)
    return {**payload, "manifest": str(target)}


def verify_manifest(manifest_value: str | Path) -> dict[str, Any]:
    manifest_path = Path(manifest_value).expanduser().resolve()
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read release manifest: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("files"), list):
        raise ValueError("release manifest is malformed")
    root = manifest_path.parent.resolve()
    errors: list[str] = []
    current_entries: list[dict[str, Any]] = []

    expected_paths: set[str] = set()
    for entry in payload["files"]:
        if not isinstance(entry, dict):
            errors.append("manifest contains a non-object file entry")
            continue
        relative = str(entry.get("path", ""))
        if not relative or relative.startswith("/") or ".." in Path(relative).parts:
            errors.append(f"unsafe manifest path: {relative!r}")
            continue
        expected_paths.add(relative)
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            errors.append(f"manifest path escapes release root: {relative}")
            continue
        if not path.is_file() or path.is_symlink():
            errors.append(f"missing or unsafe evidence file: {relative}")
            continue
        actual_size = path.stat().st_size
        actual_hash = sha256_file(path)
        if actual_size != entry.get("bytes"):
            errors.append(f"size mismatch: {relative}")
        if actual_hash != entry.get("sha256"):
            errors.append(f"sha256 mismatch: {relative}")
        current = {
            "path": relative,
            "bytes": actual_size,
            "sha256": actual_hash,
        }
        status = _json_status(path)
        if status:
            current["json_status"] = status
        current_entries.append(current)

    actual_paths = {path.relative_to(root).as_posix() for path in _files(root)}
    extras = sorted(actual_paths - expected_paths)
    missing_from_disk = sorted(expected_paths - actual_paths)
    if extras:
        errors.append("unmanifested files: " + ", ".join(extras[:20]))
    if missing_from_disk:
        errors.append("missing files: " + ", ".join(missing_from_disk[:20]))

    encoded_entries = json.dumps(current_entries, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    current_set_hash = hashlib.sha256(encoded_entries).hexdigest()
    if current_set_hash != payload.get("evidence_set_sha256"):
        errors.append("evidence-set fingerprint mismatch")

    return {
        "ok": not errors,
        "manifest": str(manifest_path),
        "root": str(root),
        "checked_files": len(current_entries),
        "evidence_set_sha256": current_set_hash,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or verify an EVAVO release evidence manifest")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--root", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--manifest", required=True)
    args = parser.parse_args()

    try:
        result = create_manifest(args.root) if args.command == "create" else verify_manifest(args.manifest)
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
