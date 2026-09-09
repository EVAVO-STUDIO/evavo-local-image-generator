#!/usr/bin/env python3
"""Generate and technically validate golden Kokoro speech samples."""

from __future__ import annotations

import argparse
import array
import json
import math
import os
import sys
import wave
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from evavo_local_image_generator.backends import KokoroBackend


TEXTS = {
    "neutral": "At first light, the harbour was almost silent. Rain moved across the roofs in narrow sheets, and a tug sounded once beyond the fog.",
    "numbers": "Delivery is scheduled for seven forty-five a.m. on Thursday, the eighteenth of September, twenty twenty-six. The invoice total is twelve thousand four hundred and eighty-seven dollars and thirty cents.",
    "expressive": "No. Leave it there. I said leave it there! Then, after a long pause, he lowered his voice. We can still fix this.",
}


def wav_metrics(path: Path) -> Dict[str, Any]:
    with wave.open(str(path), "rb") as audio:
        channels = audio.getnchannels()
        sample_rate = audio.getframerate()
        sample_width = audio.getsampwidth()
        frames = audio.getnframes()
        raw = audio.readframes(frames)
    result: Dict[str, Any] = {
        "channels": channels,
        "sample_rate_hz": sample_rate,
        "sample_width_bytes": sample_width,
        "frames": frames,
        "duration_s": round(frames / max(sample_rate, 1), 3),
    }
    if sample_width != 2 or not raw:
        result["analysis_warning"] = "peak/clipping analysis currently expects 16-bit PCM WAV"
        return result
    samples = array.array("h")
    samples.frombytes(raw)
    if sys.byteorder != "little":
        samples.byteswap()
    peak = max(abs(value) for value in samples) / 32767.0 if samples else 0.0
    clipped = sum(1 for value in samples if abs(value) >= 32734)
    rms = math.sqrt(sum(float(value) * float(value) for value in samples) / len(samples)) / 32767.0 if samples else 0.0
    result.update(
        peak=round(peak, 6),
        peak_dbfs=round(20 * math.log10(peak), 3) if peak > 0 else -120.0,
        rms=round(rms, 6),
        rms_dbfs=round(20 * math.log10(rms), 3) if rms > 0 else -120.0,
        clipping_pct=round(clipped * 100.0 / max(len(samples), 1), 6),
    )
    return result


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Kokoro golden-text quality test")
    parser.add_argument("--endpoint", default=os.getenv("KOKORO_ENDPOINT", "http://127.0.0.1:8880"))
    parser.add_argument("--voices", default=os.getenv("KOKORO_TEST_VOICES", "af_heart,af_bella,bf_emma"))
    parser.add_argument("--texts", default="neutral,numbers,expressive")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--output", default=str(Path(".evavo") / "quality-results" / "kokoro"))
    args = parser.parse_args()

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
    invalid_texts = [name for name in text_ids if name not in TEXTS]
    if invalid_texts:
        parser.error(f"unknown text ids: {', '.join(invalid_texts)}")
    if not voices:
        print("ERROR: no Kokoro voices available for testing", file=sys.stderr)
        return 3

    run_dir = Path(args.output).expanduser().resolve() / datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    report: Dict[str, Any] = {"health": health, "results": [], "failures": []}

    for voice in voices:
        for text_id in text_ids:
            target = run_dir / voice / f"{text_id}.wav"
            try:
                generated = backend.synthesize(TEXTS[text_id], target, voice=voice, speed=args.speed, response_format="wav")
                metrics = wav_metrics(target)
                result = {"voice": voice, "text_id": text_id, "generation": generated, "metrics": metrics}
                report["results"].append(result)
                print(f"PASS {voice} / {text_id}: {metrics['duration_s']}s, clipping {metrics.get('clipping_pct', 'n/a')}%")
            except Exception as exc:
                report["failures"].append({"voice": voice, "text_id": text_id, "error": str(exc)})
                print(f"FAIL {voice} / {text_id}: {exc}", file=sys.stderr)

    report["ok"] = not report["failures"]
    report_path = run_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Kokoro quality report: {report_path}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
