# EVAVO VAE Quality Evaluation

EVAVO uses the checkpoint's baked VAE by default. An external VAE is an explicit decode experiment, not a universal quality switch.

## Why evaluate a VAE separately

A VAE affects the conversion between latent space and the final image. It can materially change:

- fine colour response
- highlight and shadow reconstruction
- saturation
- skin and material texture
- small high-frequency detail
- decode artifacts

It does **not** replace checkpoint selection, prompt quality, sampling policy or a high-resolution detail pass.

The controlled VAE path therefore changes only final decoding while keeping the checkpoint, conditioning, seed and sampler recipe fixed.

## Backend contract

The canonical quality backend accepts:

```text
vae_name
```

When supplied on the built-in graph it:

1. validates the name against the live ComfyUI `VAELoader` inventory
2. inserts one core `VAELoader`
3. reroutes only the canonical `VAEDecode` node to the selected VAE
4. leaves checkpoint model/CLIP conditioning and sampling unchanged
5. preflights the resulting graph
6. returns the selected VAE in the generation receipt

Automatic VAE injection into arbitrary custom workflows is rejected. Put `VAELoader` into the custom workflow itself when the workflow owns its decode topology.

## Compare baked vs external VAE

First inspect what ComfyUI can see:

```powershell
.\RUN-MODEL-INVENTORY.ps1
```

Then compare one or more exact `VAELoader` inventory names:

```powershell
.\RUN-VAE-SWEEP.ps1 `
  -Vaes "sdxl-vae-fp16-fix.safetensors,taesdxl"
```

The sweep always includes:

```text
checkpoint_vae   baked VAE from the selected checkpoint
```

as the baseline.

Default controlled comparison:

```text
sampling profile  quality
prompts           product, portrait, landscape, interior
seed              1337
environment        frozen
LoRA               none
```

For stronger evidence:

```powershell
.\RUN-VAE-SWEEP.ps1 `
  -Vaes "sdxl-vae-fp16-fix.safetensors,taesdxl" `
  -Prompts "product,portrait,landscape,interior,game_art" `
  -Seeds "1337,424242"
```

## Frozen comparison rule

`vae-sweep.py` runs with `use_environment=false`.

That means ambient:

```text
EVAVO_IMAGE_QUALITY_PROFILE
EVAVO_IMAGE_STEPS
EVAVO_IMAGE_CFG
EVAVO_IMAGE_LORA
EVAVO_IMAGE_VAE
EVAVO_COMFYUI_WORKFLOW
```

do not silently alter the comparison.

Only the VAE candidate changes.

## Provenance

`runtime-snapshot.py` now attests VAE identity as well as checkpoint/LoRA identity.

File-backed VAEs are recorded with full SHA-256.

Approximate ComfyUI VAEs such as `taesdxl` are represented by the actual encoder and decoder component files under `models/vae_approx`; both components must be found and hashed before the VAE receipt is considered complete.

`pixel_space` is recorded as a built-in implementation rather than inventing a model-file checksum.

The parallel `C:\AI\ComfyUI-next` path can attest VAEs shared from the existing model library through the migration receipt and explicit model-root evidence.

## HTTP / gateway usage

The gateway supports the same explicit override:

```json
{
  "prompt": "Minimal black anodized aluminium speaker, precise geometry, controlled studio light",
  "quality_profile": "quality",
  "seed": 1337,
  "vae_name": "sdxl-vae-fp16-fix.safetensors",
  "use_environment": false
}
```

`use_environment` must be a real JSON boolean. The string `"false"` is rejected instead of being treated as truthy.

Task status exposes:

```text
vae
use_environment
checkpoint
seed
workflow_sha256
quality_profile
render_passes
output dimensions
```

## Batch usage

Normal batch CLI:

```powershell
python generate-batch.py `
  --prompts "premium product still life, precise metal texture, soft studio light" `
  --quality-profile quality `
  --vae "sdxl-vae-fp16-fix.safetensors" `
  --seed 1337 `
  --wait
```

Versioned plans use:

```json
{
  "vae_name": "sdxl-vae-fp16-fix.safetensors"
}
```

inside `defaults` or an item's `options`.

The v1 batch-plan schema includes this field and frozen plans suppress ambient VAE overrides.

## Review criteria

Do not judge a VAE only from perceived sharpness. Compare at fit-to-screen and 100% zoom for:

- natural colour
- shadow/highlight reconstruction
- skin/material texture
- fine edge integrity
- saturation restraint
- gradient banding
- speckling or decode noise
- overall production usability

A VAE that looks superficially sharper but produces harsher gradients, incorrect skin or unstable colour is not automatically better.

## Promotion rule

Keep the checkpoint VAE unless the external VAE is consistently better across relevant fixed prompts and seeds **and** its exact runtime/model evidence is complete.

No VAE sweep or inventory command changes the production default automatically.
