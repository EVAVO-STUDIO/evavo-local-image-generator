#!/usr/bin/env python3
"""Measure EVAVO image-profile performance on the real local ComfyUI GPU.

This benchmark is intentionally sequential. It holds checkpoint, prompt and
seed constant while sampling NVIDIA telemetry during each render. Results are
performance evidence only; they never promote an image profile or increase
batch concurrency automatically.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import statistics
import struct
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from evavo_local_image_generator.backends import ComfyUIBackend
from evavo_local_image_generator.prompt_quality import load_prompt_corpus
from evavo_local_image_generator.quality_profiles import profile_names

ROOT = Path(__file__).resolve().parent
DEFAULT_CORPUS = ROOT / "config" / "quality-golden-prompts-v1.json"
DEFAULT_OUTPUT = ROOT / ".evavo" / "quality-results" / "performance"
DEFAULT_PROFILES = "quality,hero,detail"


def _stamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    os.replace(temp, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _png_dimensions(path: Path) -> tuple[int | None, int | None]:
    try:
        with path.open("rb") as handle:
            head = handle.read(24)
        if head.startswith(b"\x89PNG\r\n\x1a\n") and len(head) >= 24:
            return struct.unpack(">II", head[16:24])
    except OSError:
        pass
    return None, None


def _parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _safe_float(value: str) -> float | None:
    text = str(value).strip()
    if not text or text.lower() in {"n/a", "na", "not supported", "[not supported]", "-"}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def parse_nvidia_sample(line: str) -> dict[str, float | None]:
    """Parse one no-units nvidia-smi telemetry row."""
    parts = next(csv.reader([line], skipinitialspace=True), [])
    parts = [part.strip() for part in parts]
    if len(parts) < 5:
        raise ValueError(f"expected 5 nvidia-smi telemetry fields, got {len(parts)}")
    return {
        "gpu_util_pct": _safe_float(parts[0]),
        "memory_used_mib": _safe_float(parts[1]),
        "memory_total_mib": _safe_float(parts[2]),
        "temperature_c": _safe_float(parts[3]),
        "power_w": _safe_float(parts[4]),
    }


def _run(argv: list[str], timeout: float = 10.0) -> subprocess.CompletedProcess[str]:
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "timeout": timeout,
    }
    if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return subprocess.run(argv, **kwargs)


def gpu_identity(nvidia_smi: str, gpu_index: int) -> dict[str, Any]:
    result = _run(
        [
            nvidia_smi,
            "--query-gpu=index,name,uuid,driver_version,memory.total",
            "--format=csv,noheader,nounits",
            "-i",
            str(gpu_index),
        ]
    )
    if result.returncode != 0:
        raise RuntimeError(f"nvidia-smi identity query failed: {result.stderr.strip() or result.stdout.strip()}")
    rows = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(rows) != 1:
        raise RuntimeError(f"nvidia-smi identity query returned {len(rows)} rows for GPU {gpu_index}")
    parts = next(csv.reader([rows[0]], skipinitialspace=True), [])
    parts = [part.strip() for part in parts]
    if len(parts) < 5:
        raise RuntimeError("nvidia-smi identity row is incomplete")
    memory = _safe_float(parts[4])
    return {
        "index": int(parts[0]),
        "name": parts[1],
        "uuid": parts[2],
        "driver_version": parts[3],
        "memory_total_mib": memory,
        "memory_total_gib": round(memory / 1024.0, 3) if memory is not None else None,
    }


@dataclass
class TelemetrySample:
    t_s: float
    gpu_util_pct: float | None
    memory_used_mib: float | None
    memory_total_mib: float | None
    temperature_c: float | None
    power_w: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "t_s": round(self.t_s, 4),
            "gpu_util_pct": self.gpu_util_pct,
            "memory_used_mib": self.memory_used_mib,
            "memory_total_mib": self.memory_total_mib,
            "temperature_c": self.temperature_c,
            "power_w": self.power_w,
        }


class NvidiaSampler:
    def __init__(self, nvidia_smi: str, gpu_index: int, interval: float = 0.25):
        self.nvidia_smi = nvidia_smi
        self.gpu_index = gpu_index
        self.interval = max(0.1, min(float(interval), 5.0))
        self.samples: list[TelemetrySample] = []
        self.errors: list[str] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._started = 0.0

    def _sample_once(self) -> None:
        result = _run(
            [
                self.nvidia_smi,
                "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
                "--format=csv,noheader,nounits",
                "-i",
                str(self.gpu_index),
            ],
            timeout=5.0,
        )
        if result.returncode != 0:
            self.errors.append((result.stderr.strip() or result.stdout.strip() or "nvidia-smi sample failed")[:1000])
            return
        rows = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not rows:
            self.errors.append("nvidia-smi returned no telemetry row")
            return
        try:
            parsed = parse_nvidia_sample(rows[0])
        except ValueError as exc:
            self.errors.append(str(exc))
            return
        self.samples.append(
            TelemetrySample(
                t_s=time.perf_counter() - self._started,
                gpu_util_pct=parsed["gpu_util_pct"],
                memory_used_mib=parsed["memory_used_mib"],
                memory_total_mib=parsed["memory_total_mib"],
                temperature_c=parsed["temperature_c"],
                power_w=parsed["power_w"],
            )
        )

    def _loop(self) -> None:
        while not self._stop.is_set():
            started = time.perf_counter()
            try:
                self._sample_once()
            except Exception as exc:  # telemetry must not kill the render
                self.errors.append(str(exc)[:1000])
            spent = time.perf_counter() - started
            self._stop.wait(max(0.01, self.interval - spent))

    def start(self) -> None:
        self.samples = []
        self.errors = []
        self._stop.clear()
        self._started = time.perf_counter()
        self._thread = threading.Thread(target=self._loop, name="evavo-nvidia-telemetry", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(2.0, self.interval * 4))
        self._thread = None


def _values(samples: Iterable[TelemetrySample], field: str) -> list[float]:
    values: list[float] = []
    for sample in samples:
        value = getattr(sample, field)
        if value is not None and math.isfinite(value):
            values.append(float(value))
    return values


def summarize_telemetry(samples: list[TelemetrySample]) -> dict[str, Any]:
    util = _values(samples, "gpu_util_pct")
    memory = _values(samples, "memory_used_mib")
    memory_total = _values(samples, "memory_total_mib")
    temp = _values(samples, "temperature_c")
    power = _values(samples, "power_w")

    def mean(values: list[float]) -> float | None:
        return round(statistics.fmean(values), 4) if values else None

    def peak(values: list[float]) -> float | None:
        return round(max(values), 4) if values else None

    total = max(memory_total) if memory_total else None
    peak_memory = max(memory) if memory else None
    peak_memory_pct = (peak_memory / total * 100.0) if peak_memory is not None and total else None
    return {
        "sample_count": len(samples),
        "mean_gpu_util_pct": mean(util),
        "peak_gpu_util_pct": peak(util),
        "mean_memory_used_mib": mean(memory),
        "peak_memory_used_mib": peak(memory),
        "memory_total_mib": round(total, 4) if total is not None else None,
        "peak_memory_util_pct": round(peak_memory_pct, 4) if peak_memory_pct is not None else None,
        "mean_temperature_c": mean(temp),
        "peak_temperature_c": peak(temp),
        "mean_power_w": mean(power),
        "peak_power_w": peak(power),
    }


def summarize_profile(runs: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [run for run in runs if run.get("status") == "completed"]
    elapsed = [float(run["elapsed_s"]) for run in completed]
    seconds_mp = [float(run["seconds_per_megapixel"]) for run in completed]
    images_hour = [float(run["images_per_hour"]) for run in completed]
    peak_memory = [
        float(run["telemetry"]["peak_memory_used_mib"])
        for run in completed
        if run.get("telemetry", {}).get("peak_memory_used_mib") is not None
    ]
    mean_util = [
        float(run["telemetry"]["mean_gpu_util_pct"])
        for run in completed
        if run.get("telemetry", {}).get("mean_gpu_util_pct") is not None
    ]
    peak_temp = [
        float(run["telemetry"]["peak_temperature_c"])
        for run in completed
        if run.get("telemetry", {}).get("peak_temperature_c") is not None
    ]
    peak_power = [
        float(run["telemetry"]["peak_power_w"])
        for run in completed
        if run.get("telemetry", {}).get("peak_power_w") is not None
    ]

    def median(values: list[float]) -> float | None:
        return round(statistics.median(values), 4) if values else None

    def mean(values: list[float]) -> float | None:
        return round(statistics.fmean(values), 4) if values else None

    return {
        "completed_runs": len(completed),
        "failed_runs": len(runs) - len(completed),
        "median_elapsed_s": median(elapsed),
        "mean_elapsed_s": mean(elapsed),
        "median_seconds_per_megapixel": median(seconds_mp),
        "median_images_per_hour": median(images_hour),
        "peak_memory_used_mib": round(max(peak_memory), 4) if peak_memory else None,
        "mean_gpu_util_pct": mean(mean_util),
        "peak_temperature_c": round(max(peak_temp), 4) if peak_temp else None,
        "peak_power_w": round(max(peak_power), 4) if peak_power else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure sequential EVAVO SDXL profile performance with NVIDIA telemetry")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8188")
    parser.add_argument("--checkpoint", required=True, help="Explicit checkpoint name reported by active ComfyUI")
    parser.add_argument("--profiles", default=DEFAULT_PROFILES)
    parser.add_argument("--prompt", default="product", help="Prompt ID from the versioned golden corpus")
    parser.add_argument("--prompt-corpus", default=str(DEFAULT_CORPUS))
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=1, help="Unrecorded quality-profile warmup renders before measurement")
    parser.add_argument("--gpu-index", type=int, default=0)
    parser.add_argument("--telemetry-interval", type=float, default=0.25)
    parser.add_argument("--timeout", type=float, default=1200.0)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--require-gpu-telemetry", action="store_true")
    args = parser.parse_args()

    if not 0 <= args.seed <= (2**63 - 1):
        parser.error("--seed must be between 0 and 2^63-1")
    if not 1 <= args.repeats <= 20:
        parser.error("--repeats must be between 1 and 20")
    if not 0 <= args.warmup <= 5:
        parser.error("--warmup must be between 0 and 5")
    if not 0.1 <= args.telemetry_interval <= 5.0:
        parser.error("--telemetry-interval must be between 0.1 and 5 seconds")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    if args.gpu_index < 0:
        parser.error("--gpu-index must be >= 0")

    profiles = _parse_csv(args.profiles)
    invalid = [name for name in profiles if name not in profile_names() or name == "custom"]
    if invalid:
        parser.error(f"unknown/non-benchmark profiles: {', '.join(invalid)}")

    try:
        corpus = load_prompt_corpus(args.prompt_corpus)
    except ValueError as exc:
        parser.error(str(exc))
    prompts = corpus["prompts"]
    if args.prompt not in prompts:
        parser.error(f"unknown golden prompt {args.prompt!r}; available: {', '.join(sorted(prompts))}")
    prompt_spec = prompts[args.prompt]

    nvidia_smi = shutil.which("nvidia-smi")
    gpu: dict[str, Any] | None = None
    telemetry_available = False
    telemetry_error: str | None = None
    if nvidia_smi:
        try:
            gpu = gpu_identity(nvidia_smi, args.gpu_index)
            telemetry_available = True
        except Exception as exc:
            telemetry_error = str(exc)
    else:
        telemetry_error = "nvidia-smi not found on PATH"
    if args.require_gpu_telemetry and not telemetry_available:
        print(json.dumps({"ok": False, "error": telemetry_error}, indent=2), file=sys.stderr)
        return 3

    backend = ComfyUIBackend(args.endpoint)
    try:
        health = backend.health()
        sampling = backend.sampling_inventory()
        checkpoints = backend.checkpoints()
    except RuntimeError as exc:
        print(f"ERROR: ComfyUI is not ready: {exc}", file=sys.stderr)
        return 3
    if args.checkpoint not in checkpoints:
        print(f"ERROR: checkpoint {args.checkpoint!r} is not in active ComfyUI inventory", file=sys.stderr)
        return 3

    run_dir = Path(args.output).expanduser().resolve() / _stamp()
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "started_at": datetime.now().astimezone().isoformat(),
        "authority": "performance evidence only; no profile promotion or concurrency mutation",
        "endpoint": backend.endpoint,
        "checkpoint": args.checkpoint,
        "health": health,
        "sampling_inventory": sampling,
        "gpu": gpu,
        "gpu_telemetry_available": telemetry_available,
        "gpu_telemetry_error": telemetry_error,
        "telemetry_interval_s": args.telemetry_interval,
        "prompt_corpus": {
            "version": corpus.get("prompt_set_version"),
            "source": corpus["source"],
            "sha256": corpus["sha256"],
        },
        "prompt_id": args.prompt,
        "prompt_sha256": prompt_spec["lint"]["prompt_sha256"],
        "seed": args.seed,
        "profiles": profiles,
        "warmup": args.warmup,
        "repeats": args.repeats,
        "runs": [],
        "failures": [],
    }
    _write_json(run_dir / "performance.json", manifest)

    # Warm up with the normal quality profile only. This avoids giving one
    # measured profile a disproportionate model-load/cache advantage while also
    # avoiding a 1536 hero warmup that spends extra VRAM/time for no evidence.
    for warmup_index in range(args.warmup):
        print(f"[warmup {warmup_index + 1}/{args.warmup}] quality | seed {args.seed}")
        try:
            queued = backend.queue_image(
                prompt_spec["prompt"],
                negative_prompt=prompt_spec["negative"],
                project_name=f"performance/warmup/{warmup_index + 1}",
                seed=args.seed,
                checkpoint=args.checkpoint,
                quality_profile="quality",
                use_environment=False,
            )
            backend.wait_for_outputs(queued["task_id"], timeout=args.timeout, interval=0.5)
        except Exception as exc:
            print(f"ERROR: warmup render failed: {exc}", file=sys.stderr)
            return 3

    total = len(profiles) * args.repeats
    ordinal = 0
    for repeat in range(1, args.repeats + 1):
        # Interleave profiles per repeat rather than rendering all of one profile
        # first, reducing slow thermal/time drift bias across a long benchmark.
        for profile in profiles:
            ordinal += 1
            print(f"[{ordinal}/{total}] repeat {repeat} | {profile} | seed {args.seed}")
            sampler = NvidiaSampler(nvidia_smi, args.gpu_index, args.telemetry_interval) if telemetry_available and nvidia_smi else None
            started = time.perf_counter()
            if sampler:
                sampler.start()
            try:
                queued = backend.queue_image(
                    prompt_spec["prompt"],
                    negative_prompt=prompt_spec["negative"],
                    project_name=f"performance/{profile}/r{repeat}",
                    seed=args.seed,
                    checkpoint=args.checkpoint,
                    quality_profile=profile,
                    use_environment=False,
                )
                target = run_dir / "images" / profile / f"repeat-{repeat}"
                files = backend.wait_and_download(queued["task_id"], target, timeout=args.timeout, interval=0.5)
                elapsed = time.perf_counter() - started
            except Exception as exc:
                if sampler:
                    sampler.stop()
                failure = {
                    "profile": profile,
                    "repeat": repeat,
                    "seed": args.seed,
                    "status": "failed",
                    "elapsed_s": round(time.perf_counter() - started, 4),
                    "error": str(exc),
                    "telemetry": summarize_telemetry(sampler.samples) if sampler else {"sample_count": 0},
                    "telemetry_errors": sampler.errors if sampler else [],
                }
                manifest["runs"].append(failure)
                manifest["failures"].append(failure)
                _write_json(run_dir / "performance.json", manifest)
                print(f"  FAIL: {exc}", file=sys.stderr)
                continue
            finally:
                if sampler and sampler._thread is not None:
                    sampler.stop()

            outputs = []
            for value in files:
                path = Path(value)
                width, height = _png_dimensions(path)
                outputs.append(
                    {
                        "path": str(path),
                        "bytes": path.stat().st_size,
                        "sha256": _sha256(path),
                        "width": width,
                        "height": height,
                    }
                )
            expected = (queued.get("output_width"), queued.get("output_height"))
            if not outputs or any((output["width"], output["height"]) != expected for output in outputs):
                failure = {
                    "profile": profile,
                    "repeat": repeat,
                    "seed": args.seed,
                    "status": "failed",
                    "elapsed_s": round(elapsed, 4),
                    "error": f"PERFORMANCE_OUTPUT_DIMENSION_MISMATCH:expected {expected}, got {[(o['width'], o['height']) for o in outputs]}",
                }
                manifest["runs"].append(failure)
                manifest["failures"].append(failure)
                _write_json(run_dir / "performance.json", manifest)
                print(f"  FAIL: {failure['error']}", file=sys.stderr)
                continue

            width = int(expected[0])
            height = int(expected[1])
            megapixels = width * height / 1_000_000.0
            telemetry = summarize_telemetry(sampler.samples) if sampler else {"sample_count": 0}
            run = {
                "profile": profile,
                "repeat": repeat,
                "seed": queued.get("seed"),
                "status": "completed",
                "elapsed_s": round(elapsed, 4),
                "images_per_hour": round(3600.0 / elapsed, 4),
                "output_width": width,
                "output_height": height,
                "megapixels": round(megapixels, 6),
                "seconds_per_megapixel": round(elapsed / megapixels, 4),
                "megapixels_per_second": round(megapixels / elapsed, 6),
                "render_passes": queued.get("render_passes"),
                "workflow_sha256": queued.get("workflow_sha256"),
                "workflow_node_count": queued.get("workflow_node_count"),
                "quality": queued.get("quality"),
                "use_environment": queued.get("use_environment"),
                "telemetry": telemetry,
                "telemetry_errors": sampler.errors if sampler else [],
                "outputs": outputs,
            }
            if args.require_gpu_telemetry and telemetry.get("sample_count", 0) < 1:
                run["status"] = "failed"
                run["error"] = "GPU telemetry was required but no samples were captured"
                manifest["failures"].append(run)
            manifest["runs"].append(run)
            _write_json(run_dir / "performance.json", manifest)

    summaries: dict[str, Any] = {}
    for profile in profiles:
        summaries[profile] = summarize_profile([run for run in manifest["runs"] if run.get("profile") == profile])
    manifest["profile_summary"] = summaries
    manifest["finished_at"] = datetime.now().astimezone().isoformat()
    manifest["ok"] = not manifest["failures"] and all(summary["completed_runs"] == args.repeats for summary in summaries.values())
    manifest["interpretation"] = {
        "quality_rule": "Do not infer aesthetic quality from speed, VRAM, utilization, temperature or power telemetry.",
        "concurrency_rule": "This benchmark is sequential and does not authorize raising batch concurrency. Benchmark concurrency separately before changing production defaults.",
    }
    _write_json(run_dir / "performance.json", manifest)

    print("\nProfile performance summary")
    for profile in profiles:
        summary = summaries[profile]
        print(
            f"  {profile:<20} median {summary['median_elapsed_s']}s | "
            f"peak VRAM {summary['peak_memory_used_mib']} MiB | "
            f"mean GPU {summary['mean_gpu_util_pct']}% | "
            f"median {summary['median_images_per_hour']} images/hour"
        )
    print(f"\nPerformance evidence: {run_dir / 'performance.json'}")
    return 0 if manifest["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
