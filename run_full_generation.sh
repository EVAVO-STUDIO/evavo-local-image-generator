#!/usr/bin/env bash
# Compatibility shim for historical Linux/VM full-generation shortcuts.
# No mounted-path assumptions, unrelated services, automatic copying or implicit
# multimodal generation remain. Arguments are forwarded to the shared image CLI.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PYTHON="$ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="${PYTHON:-python3}"
fi

exec "$PYTHON" "$ROOT/legacy_image_cli.py" --verify --repair "$@"
