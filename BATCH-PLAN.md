# EVAVO Frozen Batch Plans

Use `run-batch-plan.py` when one production batch needs different image recipes per item.

This is the deterministic batch-plan entrypoint. It masks ambient image/workflow environment variables for the duration of the run, requires an explicit checkpoint, and sends `use_environment=false` to the image backend.

`batch-plan.py` contains the lower-level plan parsing/execution engine. For production, prefer `run-batch-plan.py`.

## Files

```text
config/batch-plan-v1.schema.json
examples/batch-plan-mixed-quality-v1.json
run-batch-plan.py
batch-resume.py
```

## Dry-run first

```powershell
python run-batch-plan.py `
  --plan .\examples\batch-plan-mixed-quality-v1.json `
  --dry-run
```

Dry-run validates:

- schema version and root fields
- unique item IDs
- exactly one of `prompt` or `prompt_spec`
- supported image options only
- profile/dimension/step/CFG/denoise bounds
- seed range
- LoRA strength bounds
- prompt structure and contradictions
- custom workflow file existence
- hero/LoRA refusal for arbitrary custom workflows
- output-subdirectory confinement
- explicit checkpoint presence

No GPU task is queued.

## Execute

```powershell
python run-batch-plan.py `
  --plan .\examples\batch-plan-mixed-quality-v1.json
```

The example deliberately includes:

- a standard `quality` product render
- the same product/seed using `hero` for controlled A/B
- a separate 1871 game-art hero render

Default concurrency is `1`.

## Plan structure

```json
{
  "schema_version": 1,
  "project": "my-production-batch",
  "endpoint": "http://127.0.0.1:8188",
  "concurrency": 1,
  "wait": true,
  "wait_timeout": 900,
  "output_dir": ".evavo/my-output",
  "defaults": {
    "checkpoint": "sd_xl_base_1.0.safetensors",
    "quality_profile": "quality",
    "negative_prompt": "text, watermark, malformed geometry"
  },
  "items": [
    {
      "id": "standard",
      "prompt": "single product, three-quarter front camera, soft studio key light, precise material detail",
      "options": {"seed": 1337}
    },
    {
      "id": "hero",
      "prompt": "single product, three-quarter front camera, soft studio key light, precise material detail",
      "options": {"quality_profile": "hero", "seed": 1337}
    }
  ]
}
```

## Structured prompt items

An item may use `prompt_spec` instead of a raw prompt:

```json
{
  "id": "period-interior",
  "prompt_spec": {
    "subject": "1871 riverfront chandlery interior",
    "composition": "counter and merchant as the central midground silhouette",
    "camera": "fixed front-on side-stage camera",
    "lighting": "overcast daylight with restrained period lamp glow",
    "materials": "worn timber, brass, canvas and iron",
    "period": "historically coherent 1871",
    "style": "black-and-white engraved DOS-era game art",
    "constraints": "broad uncluttered gameplay lane in the lower third"
  },
  "options": {
    "quality_profile": "hero",
    "seed": 424242
  }
}
```

The prompt compiler is deterministic and its final positive/negative fingerprint is stored in the batch manifest.

## Per-item options

Supported plan options include:

```text
negative_prompt
quality_profile
width / height
steps / cfg_scale
sampler_name / scheduler / denoise
upscale_factor
second_pass_steps
second_pass_cfg_scale
second_pass_sampler_name
second_pass_scheduler
second_pass_denoise
latent_upscale_method
checkpoint
lora_name
lora_model_strength
lora_clip_strength
seed
workflow_path
```

Unknown options fail before queueing.

## Environment isolation

For the production entrypoint, these ambient controls are masked while the plan validates and runs:

```text
EVAVO_IMAGE_*
EVAVO_UPGRADE_LEGACY_IMAGE_DEFAULTS
EVAVO_COMFYUI_WORKFLOW
```

The resolved jobs also send:

```json
{"use_environment": false}
```

This means a workstation-level style LoRA, changed CFG, different sampler or custom workflow cannot silently alter the plan.

The plan must explicitly name its checkpoint in `defaults` or each item.

## Custom workflows

A relative `workflow_path` is resolved relative to the plan file.

Every unique workflow is preflighted against the active native ComfyUI node schema before any plan item is queued.

Automatic hero expansion and automatic LoRA insertion are refused for custom workflows. Put those nodes in the custom workflow itself.

## Output confinement

Each item is written under the plan output root. `output_subdir` must be relative and cannot contain `..` traversal.

If omitted, the item ID becomes its output subdirectory.

## Manifest and recovery

The runner writes a normal EVAVO batch manifest under `.evavo/batch-runs/` unless `--manifest` is supplied.

It includes:

- source plan path and SHA-256
- schema path/version
- normalized prompt and prompt SHA
- per-item requested recipe
- per-item output directory
- ComfyUI task receipt
- actual seed
- workflow SHA
- profile/pass/output dimensions
- LoRA receipt

The same manifest can be reconciled safely:

```powershell
python batch-resume.py --manifest "<batch-manifest.json>"
```

See `BATCH-QUALITY.md` for the explicit retry rules.

## Quality rule

Use a mixed plan to compare deliberate recipes, not to hide uncontrolled variation. For A/B comparisons, keep prompt, checkpoint and seed fixed and change one parameter at a time.
