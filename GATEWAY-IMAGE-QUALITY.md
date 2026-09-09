# EVAVO Gateway Image Quality API

Updated: 10 September 2026

The loopback EVAVO HTTP gateway now exposes the same quality-first native ComfyUI controls as `evavo-wrapper.py`. The public route remains:

```text
POST http://127.0.0.1:8000/generate/image
```

The request schema is additive and backward-compatible. Old clients can continue sending only `prompt` and optional legacy fields. New clients can select a named production quality profile, explicitly tune sampling, request the bounded two-pass hero workflow, and opt into one validated LoRA.

## Discover the active surface

Before constructing an advanced request, inspect:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/capabilities | ConvertTo-Json -Depth 10
```

The image capability reports:

```text
quality_profiles
current default quality profile
per-request quality support
hero two-pass support
LoRA support
reproducible task receipt fields
```

The actual ComfyUI sampler/scheduler/LoRA inventory remains runtime-specific; validation occurs in the canonical native backend before the graph is queued.

## Default request

```json
{
  "prompt": "Minimal black anodized aluminium desk speaker on a matte charcoal surface, precise geometry, large diffused key light, restrained commercial product photography",
  "project_name": "gateway-product"
}
```

Legacy gateway defaults `steps=24` and `cfg_scale=7` are recognized by the canonical quality backend as historical implicit defaults and upgrade to the current production `quality` profile unless the caller explicitly requests `quality_profile: "custom"`.

Current production baseline:

```text
quality
1024 x 1024
36 steps
CFG 6.5
DPM++ 2M SDE
Karras
one pass
```

## Named profile request

```json
{
  "prompt": "Controlled production prompt",
  "project_name": "gateway-quality",
  "quality_profile": "quality",
  "seed": 1337
}
```

Supported built-in names are returned by `/capabilities` and currently include:

```text
draft
quality
detail
hero
euler_reference
legacy_768_reference
```

`custom` is also accepted by the backend when the caller deliberately wants explicit custom sampling values.

## Hero request

`hero` keeps the normal SDXL-native 1024 first pass, expands the latent by 1.5x, and performs a restrained low-denoise second diffusion pass. Square output is approximately 1536 × 1536.

```json
{
  "prompt": "High-value final production image with controlled geometry and materials",
  "negative_prompt": "warped geometry, duplicate objects, smeared detail, text, watermark",
  "project_name": "gateway-hero",
  "quality_profile": "hero",
  "seed": 1337
}
```

Hero remains opt-in. It is deliberately not the universal default because the second pass costs additional GPU time and must earn promotion per subject class through the fixed-seed review workflow.

## Explicit hero tuning

Every advanced field is optional. A caller that needs an experiment can override:

```json
{
  "prompt": "Controlled hero experiment",
  "project_name": "gateway-hero-custom",
  "quality_profile": "hero",
  "seed": 1337,
  "sampler_name": "dpmpp_2m_sde",
  "scheduler": "karras",
  "denoise": 1.0,
  "upscale_factor": 1.5,
  "second_pass_steps": 18,
  "second_pass_cfg_scale": 5.5,
  "second_pass_sampler_name": "dpmpp_2m_sde",
  "second_pass_scheduler": "karras",
  "second_pass_denoise": 0.24,
  "latent_upscale_method": "bislerp"
}
```

The backend validates numeric bounds and resolves runtime-supported sampler/scheduler/upscale choices. A computed output above the quality safety ceiling is rejected instead of being allowed to become an uncontrolled VRAM workload.

## LoRA request

LoRA use is isolated and per job. Nothing is enabled globally merely because a LoRA is present on disk.

```json
{
  "prompt": "Controlled LoRA production prompt",
  "project_name": "gateway-lora",
  "quality_profile": "quality",
  "seed": 1337,
  "lora_name": "my-lora.safetensors",
  "lora_model_strength": 0.7,
  "lora_clip_strength": 0.7
}
```

The canonical backend:

- validates `lora_name` against the live ComfyUI `LoraLoader` inventory;
- bounds model/CLIP strengths to finite values;
- routes LoRA model output through every KSampler;
- routes LoRA CLIP output through positive and negative conditioning;
- preflights the modified graph before queueing;
- refuses automatic LoRA insertion into arbitrary custom workflows.

Use `RUN-LORA-SWEEP.ps1` to choose strength rather than guessing from one render.

## Hero + LoRA

The two features can be combined safely in the canonical built-in graph:

```json
{
  "prompt": "High-value final asset using a previously validated LoRA strength",
  "project_name": "gateway-hero-lora",
  "quality_profile": "hero",
  "seed": 1337,
  "lora_name": "my-lora.safetensors",
  "lora_model_strength": 0.7,
  "lora_clip_strength": 0.7
}
```

Validate the LoRA strength on the cheaper `quality` profile first. Only rerun the chosen strength on `hero` when the asset actually benefits from the additional high-resolution pass.

## Reproducible task receipt

The initial POST remains compatibility-stable and returns:

```json
{
  "task_id": "img_1234567890",
  "status": "queued",
  "progress": 0
}
```

Read the task status:

```text
GET /tasks/{task_id}/status
```

After the native graph has been submitted, status includes reproducibility/quality evidence such as:

```json
{
  "task_id": "img_1234567890",
  "status": "running",
  "progress": 25,
  "checkpoint": "sd_xl_base_1.0.safetensors",
  "seed": 1337,
  "workflow_sha256": "<64 hex chars>",
  "workflow_node_count": 10,
  "quality_profile": "hero",
  "quality_applied": true,
  "render_passes": 2,
  "output_width": 1536,
  "output_height": 1536,
  "lora": {
    "name": "my-lora.safetensors",
    "model_strength": 0.7,
    "clip_strength": 0.7
  },
  "result_ready": false
}
```

The gateway keeps internal request copies, native backend task IDs and filesystem result paths private from the public task response.

## Result

```text
GET /results/{task_id}
```

Returns:

```text
200  completed artifact
202  still queued/running
409  failed task contract
404  unknown task
410  recorded result no longer satisfies the result-path boundary
```

## Controlled quality evaluation

For production decisions, do not compare HTTP renders casually. Use the repository's governed fixed-seed tools:

```powershell
.\RUN-HERO-QUALITY.ps1
.\RUN-LORA-SWEEP.ps1 -Lora "my-lora.safetensors" -Prompt "controlled prompt"
.\FINALIZE-QUALITY-REVIEW.ps1 -Review "C:\path\to\human_review.csv" -Baseline quality
```

For a LoRA sweep use baseline `base` when finalizing the review.

These flows retain output hashes, actual submitted seed, workflow fingerprint, model/runtime evidence, technical diagnostics and explicit human scores. They never change production defaults automatically.

## Safety boundary

The gateway remains loopback-only infrastructure. Advanced quality controls do not change that boundary:

- no public bind;
- no wildcard CORS;
- request bytes and prompt lengths remain bounded;
- per-request filesystem `workflow_path` remains disabled unless the workstation owner explicitly enables and confines it;
- LoRA names resolve through ComfyUI inventory, not arbitrary request paths;
- generated result downloads remain confined to the task result directory.

See also:

```text
GATEWAY-INTEGRATION-GUIDE.md
QUALITY-PRODUCTION.md
QUALITY-ADVANCED-WORKFLOWS.md
GATEWAY-AUX-PROVIDERS.md
```
