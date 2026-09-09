# EVAVO GPU Performance Benchmark

Use measured evidence for workstation tuning. Do not infer performance from sampler names, step counts or a single successful render.

`RUN-GPU-PERFORMANCE.ps1` is the canonical performance entrypoint.

## What it measures

The benchmark renders the same versioned golden prompt with the same checkpoint and seed across selected image profiles, sequentially.

Default profiles:

```text
quality
hero
detail
```

During each measured render it samples `nvidia-smi` for:

- GPU utilization
- VRAM used / total
- temperature
- power draw

Each run records:

- elapsed seconds
- images/hour
- output width/height
- megapixels
- seconds/megapixel
- megapixels/second
- render pass count
- actual seed
- submitted workflow SHA-256
- workflow node count
- frozen quality recipe
- output file SHA-256
- telemetry summary and sampling errors

The profile summary reports medians across repeats plus observed peak VRAM/temperature/power.

## RTX 4080 12 GB baseline workflow

Run:

```powershell
.\RUN-GPU-PERFORMANCE.ps1 `
  -Checkpoint "sd_xl_base_1.0.safetensors" `
  -RequireGpuTelemetry
```

Recommended starting settings:

```text
repeats: 3
warmup: 1
seed: 1337
prompt: product
telemetry interval: 0.25 seconds
concurrency: always 1 for this benchmark
```

The warmup uses the normal `quality` profile and is not included in timing evidence. Measured profiles are interleaved per repeat to reduce long-run thermal/order bias.

## Why sequential only

This benchmark answers:

> How expensive is each image recipe on this exact runtime and GPU?

It does **not** answer:

> How many simultaneous renders should production run?

Concurrent image generation changes VRAM residency, offload behavior, queue latency and failure probability. Therefore this command never changes batch concurrency.

For the 12 GB target, keep production concurrency at `1` for hero/two-pass work unless a separate concurrency test proves useful headroom and stability.

## Reading the metrics

### Median elapsed seconds

Lower is faster for the exact same workload.

Use the median across repeats instead of one render. One run can be distorted by model loading, background work, Windows scheduling or thermal state.

### Seconds per megapixel

Useful when comparing `hero` against 1024-class profiles because hero produces more pixels. It normalizes elapsed time by final output area.

Do not treat lower seconds/megapixel as visual quality evidence.

### Peak VRAM

Peak VRAM is a production-risk signal, not a target to maximize.

If hero approaches the card's practical limit, keep concurrency at one and avoid stacking another model-heavy process on the GPU at the same time.

### GPU utilization

High utilization can indicate the GPU is being used effectively, but 100% utilization is not itself a quality or efficiency score. CPU preprocessing, VAE work, offload or driver behavior can change the pattern.

### Temperature / power

Use these to catch sustained thermal/power behavior and compare runtimes under the same workload. A faster runtime that also runs hotter is not automatically worse; the evidence should be considered with system stability and cooling.

## Compare working ComfyUI 8188 vs candidate 8189

Run the same benchmark against the current runtime:

```powershell
.\RUN-GPU-PERFORMANCE.ps1 `
  -Checkpoint "sd_xl_base_1.0.safetensors" `
  -ComfyEndpoint "http://127.0.0.1:8188" `
  -ComfyRoot "C:\AI\ComfyUI" `
  -RequireGpuTelemetry `
  -OutputRoot ".evavo\quality-results\performance\8188"
```

Then run the exact same workload against the parallel candidate:

```powershell
.\RUN-GPU-PERFORMANCE.ps1 `
  -Checkpoint "sd_xl_base_1.0.safetensors" `
  -ComfyEndpoint "http://127.0.0.1:8189" `
  -ComfyRoot "C:\AI\ComfyUI-next" `
  -RequireGpuTelemetry `
  -OutputRoot ".evavo\quality-results\performance\8189"
```

Each run writes `performance.json` and `runtime-evidence.json`.

Compare them:

```powershell
python compare-performance.py `
  ".evavo\quality-results\performance\8188\<run>\performance.json" `
  ".evavo\quality-results\performance\8189\<run>\performance.json"
```

The comparison refuses to run when these differ:

- checkpoint
- golden prompt ID / prompt SHA
- prompt-corpus SHA
- fixed seed
- repeat count
- profile list/order
- GPU identity

This prevents a runtime from appearing faster because the workload silently changed.

## Migration rule

Do not replace the working 8188 runtime just because 8189 is faster in this benchmark.

Promotion should require all of the following:

1. Same controlled performance workload is stable.
2. Fixed-seed image release evidence is visually equal or better.
3. Required custom nodes/workflows pass.
4. Model/runtime attestation is complete.
5. Full release evidence passes.
6. Human image/listening review is complete where applicable.

Use `RUN-RELEASE.ps1` for the canonical frozen full release.

## Profile interpretation

### `quality`

Use as the normal production baseline. It should give the best quality/time balance for routine work.

### `hero`

Expect materially higher latency and VRAM because it performs a 1536-class low-denoise second pass. Its purpose is higher-value final art, not higher throughput.

It should be promoted for a use case only when the fixed-seed visual review shows a meaningful improvement.

### `detail`

Useful for testing whether more first-pass sampling produces enough visible value to justify the time. Do not assume 42 steps will beat the two-pass hero path or the 36-step quality baseline.

## Telemetry limitations

`nvidia-smi` is sampled periodically, so very brief spikes can occur between samples. Treat observed peaks as measured lower bounds, not mathematically guaranteed instantaneous maxima.

Power reporting can be unsupported on some driver/device combinations. Missing power telemetry is recorded rather than fabricated.

Use `-RequireGpuTelemetry` for release-like performance evidence so missing GPU samples fail the benchmark.

## Background-process discipline

For comparable evidence:

- close unrelated GPU-intensive applications
- avoid simultaneous game/editor renders
- keep Windows power/cooling settings consistent
- do not change ComfyUI launch flags between compared runs unless that is the variable being tested
- keep checkpoint/prompt/seed/repeats identical

Record the actual runtime rather than relying on memory. `RUN-GPU-PERFORMANCE.ps1` captures model/runtime evidence outside the timed loop.

## No automatic tuning

Performance evidence is descriptive. These tools do **not** automatically:

- lower or raise image quality
- choose a winning sampler
- change the default profile
- change ComfyUI launch flags
- increase batch concurrency
- promote ComfyUI-next

Those are explicit decisions after comparing measured performance with visual-quality and reliability evidence.
