# EVAVO Production Batch Quality

`generate-batch.py` now uses the same quality controls and receipts as single-image generation.

## Quality-first defaults

- concurrency defaults to `1`
- prompts are structurally linted before anything is queued
- the backend's `quality` profile remains the normal image default
- generated task history stores a bounded `generation_receipt`
- every batch writes an atomic run manifest under `.evavo/batch-runs/` unless `--manifest` is supplied

The run manifest is local evidence and is ignored by Git.

## Normal quality batch

```powershell
python generate-batch.py `
  --prompts `
    "black anodized desk speaker, three-quarter front angle, soft diffused key light, matte charcoal surface" `
    "brushed aluminium desk lamp, three-quarter front angle, large diffused key light, neutral seamless background" `
  --negative-prompt "warped geometry, duplicate object, text, watermark" `
  --quality-profile quality `
  --seed 1337 `
  --seed-strategy increment `
  --wait
```

For two prompts the planned seeds are `1337` and `1338`.

Use `--seed-strategy same` when comparing prompts or settings against the exact same noise seed.

## Hero batch

```powershell
python generate-batch.py `
  --prompts "premium product still life, three-quarter camera, controlled studio light, precise material detail" `
  --quality-profile hero `
  --seed 1337 `
  --wait
```

The hero profile uses the governed two-pass latent path. Do not raise concurrency simply because a single hero render fits in VRAM.

## LoRA batch

```powershell
python generate-batch.py `
  --prompts "late Victorian workshop interior, fixed eye-level camera, overcast window light, worn timber and iron" `
  --quality-profile quality `
  --lora "my-style.safetensors" `
  --lora-model-strength 0.7 `
  --lora-clip-strength 0.7 `
  --seed 1337 `
  --wait
```

Evaluate a LoRA with `RUN-LORA-SWEEP.ps1` before using it broadly.

## Explicit controls

Batch generation exposes:

```text
--quality-profile
--width / --height
--steps / --cfg-scale
--sampler / --scheduler / --denoise
--upscale-factor
--second-pass-steps
--second-pass-cfg
--second-pass-sampler
--second-pass-scheduler
--second-pass-denoise
--latent-upscale-method
--checkpoint
--lora
--lora-model-strength
--lora-clip-strength
--seed
--seed-strategy same|increment
```

Custom workflows cannot use automatic hero expansion or automatic LoRA insertion. Put those nodes into the custom workflow itself so EVAVO never guesses its topology.

## Prompt lint

Structural lint errors stop the batch before any GPU work is queued. Warnings remain evidence only.

`--allow-prompt-lint-errors` exists for intentional exceptions, but should not be a permanent default.

Use `PROMPT-QUALITY.md` and `prompt-quality.py` for structured prompt design.

## Durable evidence

Each batch manifest records:

- endpoint and project
- concurrency / wait policy
- workflow path when used
- base seed and seed strategy
- normalized prompt + prompt SHA
- prompt-lint findings
- exact requested generation options
- per-item status and task ID
- full wrapper/backend result including seed, workflow SHA, profile, pass count, output dimensions and LoRA receipt

`task_history.json` stores the important recipe in `generation_receipt` so task listings do not lose reproducibility metadata.

## Recovery and resume

Start with reconciliation only:

```powershell
python batch-resume.py --manifest ".evavo\batch-runs\<run>.json"
```

Default recovery policy is deliberately non-duplicating:

- completed items are left alone
- known backend task IDs are queried
- a known queued task is **not** resubmitted
- failed/pending work is **not** retried unless explicitly requested

Retry failed items that have no known backend task ID:

```powershell
python batch-resume.py --manifest "<run.json>" --retry-failed
```

Retry pending/unknown items only when you accept the risk that the prior process may have died after queueing but before recording its task ID:

```powershell
python batch-resume.py --manifest "<run.json>" --retry-pending
```

A failed item with a real backend task ID is treated as ambiguous and requires both flags:

```powershell
python batch-resume.py `
  --manifest "<run.json>" `
  --retry-failed `
  --force-retry-identified
```

That extra friction is intentional. Recovery should not silently turn a network/wrapper failure into duplicate GPU work.

## Concurrency

For a 12 GB GPU, keep `--concurrency 1` as the normal production setting, especially for hero/two-pass jobs.

Only raise concurrency after measuring the exact checkpoint/workflow on the actual workstation. Queue throughput is not useful if VRAM pressure causes offload, OOMs or unstable latency.

## Git policy

Do not commit:

- `.evavo/` batch manifests
- generated images/audio/video
- checkpoints/LoRAs/model binaries
- task history
- machine-specific logs

Track source, prompt/config schemas, model manifests/hashes and reviewed production defaults instead.
