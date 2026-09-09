"""Ensure direct test-file execution can import the repository package.

`verify-evavo.py` intentionally executes package tests as standalone Python files.
On a clean checkout that has not been installed editable, Python places this
`tests` directory on ``sys.path`` but may not include the repository root.
Python's standard `site` initialization imports `sitecustomize` when present, so
this tiny test-only bootstrap inserts the repo root before test modules import
`evavo_local_image_generator`.

This file has no runtime effect on the installed EVAVO package.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
root_text = str(ROOT)
if root_text not in sys.path:
    sys.path.insert(0, root_text)
