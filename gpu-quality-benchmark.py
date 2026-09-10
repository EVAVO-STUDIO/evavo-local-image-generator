#!/usr/bin/env python3
"""Measure EVAVO image-profile throughput and NVIDIA GPU pressure.

This benchmark deliberately does not choose an aesthetic winner. It produces
performance evidence that must be combined with the existing fixed-seed human
review before a profile is promoted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import statistics
import struct
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from evavo_local_image_generator.backends import ComfyUIBackend
from evavo_local_image_generator.prompt_quality import load_prompt_corpus
from evavo_local_image_generator.quality_profiles import profile_names

ROOT = Path(__file__).resolve().parent
DEFAULT_CORPUS = ROOT / "config" / "quality-golden-prompts-v1.json"


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


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


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)


def _run(argv: list[str], timeout: float = 10.0) -> subprocess.CompletedProcess[str] | None:
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "timeout": timeout,
    }
    if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        return subprocess.run(argv, **kwargs)
    except (OSError, subprocess.TimeoutExpired):
        return None


def nvidia_sample(gpu_index: int = 0) -> dict[str, Any] | None:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return None
    result = _run(
        [
            executable,
            f"--id={gpu_index}",
            "--query-gpu=index,name,driver_version,memory.total,memory.used,memory.free,utilization.gpu,power.draw,temperature.gpu",
            "--format=csv,noheader,nounits",
        ],
        timeout=5.0,
    )
    if result is None or result.returncode != 0:
        return None
    line = next((value.strip() for value in result.stdout.splitlines() if value.strip()), "")
    parts = [value.strip() for value in line.split(",")]
    if len(parts) < 9:
        return None

    def number(value: str) -> float | None:
        try:
            return float(value)
        except ValueError:
            return None

    return {
        "captured_at": datetime.now().astimezone().isoformat(),
        "index": int(float(parts[0])) if number(parts[0]) is not None else gpu_index,
        "name": parts[1],
        "driver_version": parts[2],
        "memory_total_mib": number(parts[3]),
        "memory_used_mib": number(parts[4]),
        "memory_free_mib": number(parts[5]),
        "utilization_gpu_pct": number(parts[6]),
        "power_draw_w": number(parts[7]),
        "temperature_c": number(parts[8]),
    }


class NvidiaTelemetry:
    def __init__(self, gpu_index: int, interval: float):
        self.gpu_index = gpu_index
        self.interval = max(0.25, float(interval))
        self.samples: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.samples = []
        self._stop.clear()
        first = nvidia_sample(self.gpu_index)
        if first is not None:
            self.samples.append(first)
        self._thread = threading.Thread(target=self._run, name="evavo-nvidia-telemetry", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            sample = nvidia_sample(self.gpu_index)
            if sample is not None:
                self.samples.append(sample)

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(2.0, self.interval * 4))
        final = nvidia_sample(self.gpu_index)
        if final is not None:
            self.samples.append(final)
        return summarize_gpu_samples(self.samples)


def summarize_gpu_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        return {"available": False, "sample_count": 0}

    def values(name: str) -> list[float]:
        output: list[float] = []
        for sample in samples:
            value = sample.get(name)
            if isinstance(value, (int, float)):
                output.append(float(value))
        return output

    used = values("memory_used_mib")
    free = values("memory_free_mib")
    util = values("utilization_gpu_pct")
    power = values("power_draw_w")
    temp = values("temperature_c")
    return {
        "available": True,
        "sample_count": len(samples),
        "gpu": samples[0].get("name"),
        "driver_version": samples[0].get("driver_version"),
        "memory_total_mib": samples[0].get("memory_total_mib"),
        "memory_used_start_mib": used[0] if used else None,
        "memory_used_end_mib": used[-1] if used else None,
        "memory_used_peak_mib": max(used) if used else None,
        "memory_free_min_mib": min(free) if free else None,
        "utilization_peak_pct": max(util) if util else None,
        "utilization_mean_pct": round(statistics.fmean(util), 3) if util else None,
        "power_peak_w": max(power) if power else None,
        "power_mean_w": round(statistics.fmean(power), 3) if power else None,
        "temperature_peak_c": max(temp) if temp else None,
    }


def performance_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        if result.get("status") != "completed":
            continue
        grouped.setdefault(str(result.get("profile")), []).append(result)

    summary: dict[str, Any] = {}
    for profile, rows in sorted(grouped.items()):
        elapsed = [float(row["elapsed_s"]) for row in rows]
        seconds_per_mp = [float(row["seconds_per_megapixel"]) for row in rows if row.get("seconds_per_megapixel") is not None]
        peak_vram = [
            float(row["gpu"]["memory_used_peak_mib"])
            for row in rows
            if isinstance(row.get("gpu"), dict) and row["gpu"].get("memory_used_peak_mib") is not None
        ]
        median_elapsed = statistics.median(elapsed)
        summary[profile] = {
            "completed_runs": len(rows),
            "median_elapsed_s": round(median_elapsed, 4),
            "mean_elapsed_s": round(statistics.fmean(elapsed), 4),
            "images_per_hour_at_median": round(3600.0 / median_elapsed, 3) if median_elapsed > 0 else None,
            "median_seconds_per_megapixel": round(statistics.median(seconds_per_mp), 4) if seconds_per_mp else None,
            "median_peak_vram_mib": round(statistics.median(peak_vram), 2) if peak_vram else None,
            "max_peak_vram_mib": round(max(peak_vram), 2) if peak_vram else None,
            "render_passes": rows[0].get("render_passes"),
            "output_width": rows[0].get("expected_output_width"),
            "output_height": rows[0].get("expected_output_height"),
        }

    baseline = summary.get("quality")
    if baseline and baseline.get("median_elapsed_s"):
        base_time = float(baseline["median_elapsed_s"])
        for values in summary.values():
            current = values.get("median_elapsed_s")
            values["time_ratio_vs_quality"] = round(float(current) / base_time, 3) if current is not None else None
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark EVAVO image quality profiles with NVIDIA telemetry")
    parser.add_argument("--endpoint", default=os.getenv("COMFYUI_ENDPOINT", "http://127.0.0.1:8188"))
    parser.add_argument("--profiles", default="quality,hero,detail,euler_reference")
    parser.add_argument("--prompt-id", default="product")
    parser.add_argument("--prompt-corpus", default=str(DEFAULT_CORPUS))
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--checkpoint", default=os.getenv("EVAVO_COMFYUI_CHECKPOINT"))
    parser.add_argument("--gpu-index", type=int, default=0)
    parser.add_argument("--telemetry-interval", type=float, default=0.5)
    parser.add_argument("--timeout", type=float, default=1200.0)
    parser.add_argument("--output", default=str(Path(".evavo") / "quality-results" / "gpu-benchmarks"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not 1 <= args.repeats <= 20:
        parser.error("--repeats must be between 1 and 20")
    if not 0 <= args.warmup <= 5:
        parser.error("--warmup must be between 0 and 5")
    if args.telemetry_interval < 0.25:
        parser.error("--telemetry-interval must be at least 0.25 seconds")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")

    try:
        corpus = load_prompt_corpus(args.prompt_corpus)
    except ValueError as exc:
        parser.error(str(exc))
    prompt_spec = corpus["prompts"].get(args.prompt_id)
    if not isinstance(prompt_spec, dict):
        parser.error(f"unknown prompt id {args.prompt_id!r}; available: {', '.join(sorted(corpus['prompts']))}")

    profiles = _csv(args.profiles)
    invalid = [name for name in profiles if name not in profile_names()]
    if invalid:
        parser.error(f"unknown profiles: {', '.join(invalid)}")
    plan = [
        {"profile": profile, "repeat": repeat, "seed": args.seed}
        for profile in profiles
        for repeat in range(1, args.repeats + 1)
    ]
    if args.dry_run:
        print(
            json.dumps(
                {
                    "ok": True,
                    "environment_mode": "frozen",
                    "prompt_id": args.prompt_id,
                    "prompt_corpus_sha256": corpus["sha256"],
                    "warmup": args.warmup,
                    "plan": plan,
                },
                indent=2,
            )
        )
        return 0

    backend = ComfyUIBackend(args.endpoint)
    try:
        health = backend.health()
        sampling = backend.sampling_inventory()
    except Exception as exc:
        print(f"ERROR: ComfyUI is not ready: {exc}", file=sys.stderr)
        return 3

    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    run_dir = Path(args.output).expanduser().resolve() / f"{stamp}-{args.prompt_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "benchmark_type": "gpu_quality_performance",
        "started_at": datetime.now().astimezone().isoformat(),
        "endpoint": backend.endpoint,
        "environment_mode": "frozen",
        "checkpoint": args.checkpoint,
        "prompt_id": args.prompt_id,
        "prompt_sha256": prompt_spec["lint"]["prompt_sha256"],
        "prompt_corpus": {
            "version": corpus.get("prompt_set_version"),
            "source": corpus["source"],
            "sha256": corpus["sha256"],
        },
        "health": health,
        "sampling_inventory": sampling,
        "gpu_before": nvidia_sample(args.gpu_index),
        "warmup_runs": [],
        "results": [],
        "failures": [],
    }
    _write_json(run_dir / "manifest.json", manifest)

    for index in range(args.warmup):
        try:
            queued = backend.queue_image(
                prompt_spec["prompt"],
                negative_prompt=prompt_spec["negative"],
                project_name=f"gpu-benchmark/warmup/{index + 1}",
                seed=args.seed,
                checkpoint=args.checkpoint,
                quality_profile="quality",
                use_environment=False,
            )
            files = backend.wait_and_download(
                queued["task_id"], run_dir / "warmup" / str(index + 1), timeout=args.timeout
            )
            manifest["warmup_runs"].append(
                {"status": "completed", "task_id": queued["task_id"], "outputs": files}
            )
        except Exception as exc:
            manifest["warmup_runs"].append({"status": "failed", "error": str(exc)})
            manifest["failures"].append({"phase": "warmup", "repeat": index + 1, "error": str(exc)})
            _write_json(run_dir / "manifest.json", manifest)
            print(f"ERROR: warmup failed: {exc}", file=sys.stderr)
            return 1

    for index, item in enumerate(plan, 1):
        print(f"[{index}/{len(plan)}] {item['profile']} repeat {item['repeat']} seed {item['seed']}")
        telemetry = NvidiaTelemetry(args.gpu_index, args.telemetry_interval)
        started = time.perf_counter()
        telemetry.start()
        try:
            queued = backend.queue_image(
                prompt_spec["prompt"],
                negative_prompt=prompt_spec["negative"],
                project_name=f"gpu-benchmark/{args.prompt_id}/{item['profile']}/{item['repeat']}",
                seed=item["seed"],
                checkpoint=args.checkpoint,
                quality_profile=item["profile"],
                use_environment=False,
            )
            target = run_dir / "images" / item["profile"] / str(item["repeat"])
            files = backend.wait_and_download(queued["task_id"], target, timeout=args.timeout)
            elapsed = time.perf_counter() - started
            gpu = telemetry.stop()
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
            if not outputs:
                raise RuntimeError("GPU benchmark render produced no downloadable output")
            output_width = queued.get("output_width") or outputs[0].get("width")
            output_height = queued.get("output_height") or outputs[0].get("height")
            megapixels = None
            if isinstance(output_width, int) and isinstance(output_height, int):
                megapixels = (output_width * output_height) / 1_000_000.0
            result = {
                **item,
                "prompt_id": args.prompt_id,
                "status": "completed",
                "elapsed_s": round(elapsed, 4),
                "megapixels": round(megapixels, 6) if megapixels else None,
                "seconds_per_megapixel": round(elapsed / megapixels, 4) if megapixels else None,
                "submitted_seed": queued.get("seed"),
                "checkpoint": queued.get("checkpoint"),
                "quality": queued.get("quality"),
                "quality_applied": queued.get("quality_applied"),
                "render_passes": queued.get("render_passes"),
                "expected_output_width": queued.get("output_width"),
                "expected_output_height": queued.get("output_height"),
                "workflow_sha256": queued.get("workflow_sha256"),
                "workflow_node_count": queued.get("workflow_node_count"),
                "lora": queued.get("lora"),
                "gpu": gpu,
                "outputs": outputs,
            }
            if queued.get("lora") is not None:
                raise RuntimeError("GPU_BENCHMARK_AMBIENT_LORA_LEAK:controlled benchmark unexpectedly applied a LoRA")
            manifest["results"].append(result)
        except Exception as exc:
            if telemetry._thread is not None and telemetry._thread.is_alive():
                gpu = telemetry.stop()
            else:
                gpu = summarize_gpu_samples(telemetry.samples)
            failure = {**item, "status": "failed", "error": str(exc), "gpu": gpu}
            manifest["failures"].append(failure)
            print(f"  FAIL: {exc}", file=sys.stderr)
        _write_json(run_dir / "manifest.json", manifest)

    manifest["gpu_after"] = nvidia_sample(args.gpu_index)
    manifest["performance_summary"] = performance_summary(manifest["results"])
    manifest["performance_warning"] = (
        "Throughput and VRAM evidence do not measure visual quality. Combine this report with the fixed-seed human review before profile promotion."
    )
    manifest["finished_at"] = datetime.now().astimezone().isoformat()
    manifest["ok"] = not manifest["failures"] and len(manifest["results"]) == len(plan)
    _write_json(run_dir / "manifest.json", manifest)

    print(json.dumps(manifest["performance_summary"], indent=2, ensure_ascii=False))
    print(f"GPU benchmark manifest: {run_dir / 'manifest.json'}")
    return 0 if manifest["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
