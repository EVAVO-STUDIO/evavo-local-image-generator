"""Technical audio diagnostics for local EVAVO speech quality gates.

Metrics are descriptive signals, not a substitute for listening. The module is
stdlib-only so release checks do not depend on an audio-analysis framework.
"""

from __future__ import annotations

import array
import math
import sys
import wave
from pathlib import Path
from typing import Any


def _dbfs(value: float) -> float:
    return 20.0 * math.log10(value) if value > 0 else -120.0


def _leading_trailing_silence(samples: list[float], sample_rate: int, channels: int, threshold: float = 0.005) -> tuple[float, float]:
    if not samples or sample_rate <= 0 or channels <= 0:
        return 0.0, 0.0
    frame_count = len(samples) // channels
    if frame_count <= 0:
        return 0.0, 0.0

    def frame_peak(frame: int) -> float:
        start = frame * channels
        return max(abs(samples[start + channel]) for channel in range(channels))

    first = 0
    while first < frame_count and frame_peak(first) < threshold:
        first += 1
    last = frame_count - 1
    while last >= first and frame_peak(last) < threshold:
        last -= 1
    leading = first / sample_rate
    trailing = (frame_count - 1 - last) / sample_rate if last >= first else frame_count / sample_rate
    return leading, trailing


def wav_diagnostics(path: str | Path, *, word_count: int | None = None) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    with wave.open(str(source), "rb") as audio:
        channels = audio.getnchannels()
        sample_rate = audio.getframerate()
        sample_width = audio.getsampwidth()
        frames = audio.getnframes()
        compression = audio.getcomptype()
        raw = audio.readframes(frames)

    duration = frames / max(sample_rate, 1)
    result: dict[str, Any] = {
        "channels": channels,
        "sample_rate_hz": sample_rate,
        "sample_width_bytes": sample_width,
        "bit_depth": sample_width * 8,
        "frames": frames,
        "duration_s": round(duration, 6),
        "compression": compression,
        "file_bytes": source.stat().st_size,
    }
    if word_count is not None and duration > 0:
        result["word_count"] = int(word_count)
        result["effective_wpm"] = round(float(word_count) * 60.0 / duration, 3)

    if sample_width != 2 or not raw:
        result["analysis_warning"] = "amplitude/silence analysis currently expects 16-bit PCM WAV"
        return result

    values = array.array("h")
    values.frombytes(raw)
    if sys.byteorder != "little":
        values.byteswap()
    if not values:
        result["analysis_warning"] = "WAV contains no PCM samples"
        return result

    normalized = [float(value) / 32768.0 for value in values]
    peak = max(abs(value) for value in normalized)
    rms = math.sqrt(sum(value * value for value in normalized) / len(normalized))
    dc = sum(normalized) / len(normalized)
    clipped = sum(1 for value in values if abs(value) >= 32734)
    leading, trailing = _leading_trailing_silence(normalized, sample_rate, channels)
    crest_db = _dbfs(peak) - _dbfs(rms) if peak > 0 and rms > 0 else 0.0

    result.update(
        peak=round(peak, 8),
        peak_dbfs=round(_dbfs(peak), 4),
        rms=round(rms, 8),
        rms_dbfs=round(_dbfs(rms), 4),
        crest_factor_db=round(crest_db, 4),
        clipping_pct=round(clipped * 100.0 / len(values), 8),
        dc_offset=round(dc, 8),
        dc_offset_abs=round(abs(dc), 8),
        leading_silence_s=round(leading, 6),
        trailing_silence_s=round(trailing, 6),
    )
    return result


def speech_quality_checks(metrics: dict[str, Any]) -> dict[str, Any]:
    """Return conservative pass/fail checks plus warnings for a speech WAV."""
    errors: list[str] = []
    warnings: list[str] = []

    duration = float(metrics.get("duration_s", 0.0) or 0.0)
    if duration < 0.5:
        errors.append("audio duration is below 0.5 seconds")
    if int(metrics.get("sample_rate_hz", 0) or 0) < 16000:
        errors.append("sample rate is below 16 kHz")
    if int(metrics.get("channels", 0) or 0) not in {1, 2}:
        errors.append("channel count is not mono or stereo")

    clipping = metrics.get("clipping_pct")
    if clipping is not None and float(clipping) > 0.1:
        errors.append("more than 0.1% of PCM samples are clipped")
    peak_dbfs = metrics.get("peak_dbfs")
    if peak_dbfs is not None and float(peak_dbfs) < -30.0:
        errors.append("speech peak is below -30 dBFS")
    rms_dbfs = metrics.get("rms_dbfs")
    if rms_dbfs is not None and float(rms_dbfs) < -45.0:
        errors.append("speech RMS is below -45 dBFS")
    dc = metrics.get("dc_offset_abs")
    if dc is not None and float(dc) > 0.02:
        warnings.append("absolute DC offset exceeds 0.02")
    leading = metrics.get("leading_silence_s")
    if leading is not None and float(leading) > 1.5:
        warnings.append("leading silence exceeds 1.5 seconds")
    trailing = metrics.get("trailing_silence_s")
    if trailing is not None and float(trailing) > 2.0:
        warnings.append("trailing silence exceeds 2 seconds")
    wpm = metrics.get("effective_wpm")
    if wpm is not None:
        value = float(wpm)
        if value < 55.0 or value > 360.0:
            errors.append(f"effective speaking rate is implausible at {value:.1f} WPM")
        elif value < 80.0 or value > 260.0:
            warnings.append(f"speaking rate is unusual at {value:.1f} WPM")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "error_count": len(errors),
        "warning_count": len(warnings),
    }
