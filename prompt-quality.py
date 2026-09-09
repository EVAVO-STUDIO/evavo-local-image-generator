#!/usr/bin/env python3
"""CLI for deterministic EVAVO image-prompt compilation and linting."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evavo_local_image_generator.prompt_quality import compile_prompt, lint_prompt, load_prompt_corpus


def _read_spec(path: str) -> dict:
    source = Path(path).expanduser().resolve()
    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read prompt spec {source}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("prompt spec JSON root must be an object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint or compile EVAVO image prompts")
    sub = parser.add_subparsers(dest="command", required=True)

    lint_parser = sub.add_parser("lint", help="lint one positive/negative prompt pair")
    lint_parser.add_argument("--prompt", required=True)
    lint_parser.add_argument("--negative", default="")
    lint_parser.add_argument("--strict-warnings", action="store_true")

    compile_parser = sub.add_parser("compile", help="compile a structured JSON prompt specification")
    compile_parser.add_argument("--spec", required=True)
    compile_parser.add_argument("--strict-warnings", action="store_true")

    corpus_parser = sub.add_parser("corpus", help="validate and fingerprint a prompt corpus")
    corpus_parser.add_argument("--path", default="config/quality-golden-prompts-v1.json")

    args = parser.parse_args()
    try:
        if args.command == "lint":
            result = lint_prompt(args.prompt, args.negative)
        elif args.command == "compile":
            result = compile_prompt(_read_spec(args.spec))
        else:
            corpus = load_prompt_corpus(args.path)
            result = {
                "ok": True,
                "prompt_set_version": corpus.get("prompt_set_version"),
                "source": corpus["source"],
                "sha256": corpus["sha256"],
                "prompt_ids": sorted(corpus["prompts"]),
            }
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2

    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not result.get("ok", False):
        return 1
    if getattr(args, "strict_warnings", False) and result.get("warning_count", 0):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
