#!/usr/bin/env python3
"""Generate and technically validate golden Kokoro speech samples."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from evavo_local_image_generator.audio_quality import speech_quality_checks, wav_diagnostics
from evavo_local_image_generator.backends import KokoroBackend

ROOT = Path(__file__).resolve().parent
DEFAULT_TEXT_CORPUS = ROOT / "config" / "kokoro-golden-texts-v1.json"
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?")
REVIEW_COLUMNS = (
    "naturalness_1_5",
    "pronunciation_1_5",
    "pacing_1_5",
    "emotional_fit_1_5",
    "artifact_freedom_1_5",
    "production_usability_1_5",
    "review_notes",
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_corpus(path: str | Path) -> Dict[str, Any]:
    source = Path(path).expanduser().resolve()
    try:
        raw = source.read_bytes()
        payload = json.loads(raw.decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid Kokoro text corpus {source}: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("texts"), dict):
        raise ValueError("Kokoro text corpus must contain a texts object")
    texts: Dict[str, Any] = {}
    for text_id, spec in payload["texts"].items():
        if not isinstance(text_id, str) or not text_id or not isinstance(spec, dict):
            raise ValueError("Kokoro text corpus entries must be named objects")
        text = spec.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"Kokoro text corpus entry {text_id!r} has no text")
        focus = spec.get("review_focus", [])
        if not isinstance(focus, list):
            raise ValueError(f"Kokoro text corpus entry {text_id!r} review_focus must be a list")
        texts[text_id] = {"text": text.strip(), "review_focus": [str(item) for item in focus]}
    return {
        "source": str(source),
        "sha256": _sha256_bytes(raw),
        "text_set_version": payload.get("text_set_version"),
        "texts": texts,
    }


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _write_json(path: Path, payload: Any) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)


def _write_review_csv(path: Path, results: list[Dict[str, Any]]) -> None:
    columns = [
        "voice",
        "text_id",
        "input_sha256",
        "output_sha256",
        "duration_s",
        "effective_wpm",
        "peak_dbfs",
        "rms_dbfs",
        "clipping_pct",
        "leading_silence_s",
        "trailing_silence_s",
        "review_focus",
        *REVIEW_COLUMNS,
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for result in results:
            metrics = result["metrics"]
            row = {
                "voice": result["voice"],
                "text_id": result["text_id"],
                "input_sha256": result["input_sha256"],
                "output_sha256": result["output_sha256"],
                "duration_s": metrics.get("duration_s"),
                "effective_wpm": metrics.get("effective_wpm"),
                "peak_dbfs": metrics.get("peak_dbfs"),
                "rms_dbfs": metrics.get("rms_dbfs"),
                "clipping_pct": metrics.get("clipping_pct"),
                "leading_silence_s": metrics.get("leading_silence_s"),
                "trailing_silence_s": metrics.get("trailing_silence_s"),
                "review_focus": " | ".join(result.get("review_focus", [])),
            }
            row.update({column: "" for column in REVIEW_COLUMNS})
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(description="Kokoro golden-text quality test")
    parser.add_argument("--endpoint", default=os.getenv("KOKORO_ENDPOINT", "http://127.0.0.1:8880"))
    parser.add_argument("--voices", default=os.getenv("KOKORO_TEST_VOICES", "af_heart,af_bella,bf_emma"))
    parser.add_argument("--texts", default="neutral,numbers,expressive")
    parser.add_argument("--text-corpus", default=str(DEFAULT_TEXT_CORPUS))
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--output", default=str(Path(".evavo") / "quality-results" / "kokoro"))
    args = parser.parse_args()

    try:
        corpus = _load_corpus(args.text_corpus)
    except ValueError as exc:
        parser.error(str(exc))

    backend = KokoroBackend(args.endpoint)
    try:
        health = backend.health()
        available = health.get("voices", [])
    except RuntimeError as exc:
        print(f"ERROR: Kokoro is not ready: {exc}", file=sys.stderr)
        return 3

    requested_voices = parse_csv(args.voices)
    voices = [voice for voice in requested_voices if not available or voice in available]
    if not voices and available:
        voices = list(available[:3])
    text_ids = parse_csv(args.texts)
    invalid_texts = [name for name in text_ids if name not in corpus["texts"]]
    if invalid_texts:
        parser.error(f"unknown text ids: {', '.join(invalid_texts)}")
    if not voices:
        print("ERROR: no Kokoro voices available for testing", file=sys.stderr)
        return 3

    run_dir = Path(args.output).expanduser().resolve() / datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    report: Dict[str, Any] = {
        "schema_version": 2,
        "started_at": datetime.now().astimezone().isoformat(),
        "endpoint": backend.endpoint,
        "speed": args.speed,
        "health": health,
        "text_corpus": {
            "text_set_version": corpus.get("text_set_version"),
            "source": corpus["source"],
            "sha256": corpus["sha256"],
        },
        "voices": voices,
        "text_ids": text_ids,
        "results": [],
        "failures": [],
    }
    _write_json(run_dir / "report.json", report)

    for voice in voices:
        for text_id in text_ids:
            spec = corpus["texts"][text_id]
            text = spec["text"]
            target = run_dir / voice / f"{text_id}.wav"
            try:
                generated = backend.synthesize(text, target, voice=voice, speed=args.speed, response_format="wav")
                word_count = len(WORD_RE.findall(text))
                metrics = wav_diagnostics(target, word_count=word_count)
                checks = speech_quality_checks(metrics)
                result = {
                    "voice": voice,
                    "text_id": text_id,
                    "input_sha256": _sha256_bytes(text.encode("utf-8")),
                    "output_sha256": _sha256_file(target),
                    "review_focus": spec.get("review_focus", []),
                    "generation": generated,
                    "metrics": metrics,
                    "checks": checks,
                }
                if not checks["ok"]:
                    raise RuntimeError("KOKORO_TECHNICAL_QC_FAILED:" + "; ".join(checks["errors"]))
                report["results"].append(result)
                warning_suffix = f", {checks['warning_count']} warning(s)" if checks["warning_count"] else ""
                print(
                    f"PASS {voice} / {text_id}: {metrics['duration_s']:.2f}s, "
                    f"{metrics.get('effective_wpm', 'n/a')} WPM, clipping {metrics.get('clipping_pct', 'n/a')}%{warning_suffix}"
                )
            except Exception as exc:
                report["failures"].append({"voice": voice, "text_id": text_id, "error": str(exc)})
                print(f"FAIL {voice} / {text_id}: {exc}", file=sys.stderr)
            _write_json(run_dir / "report.json", report)

    report["finished_at"] = datetime.now().astimezone().isoformat()
    report["ok"] = not report["failures"] and len(report["results"]) == len(voices) * len(text_ids)
    _write_json(run_dir / "report.json", report)
    _write_review_csv(run_dir / "human_review.csv", report["results"])

    print(f"Kokoro quality report: {run_dir / 'report.json'}")
    print(f"Kokoro listening review: {run_dir / 'human_review.csv'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
