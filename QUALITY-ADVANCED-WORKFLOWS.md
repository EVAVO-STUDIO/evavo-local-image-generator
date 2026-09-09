# EVAVO Advanced Local Generation Quality Workflows

Updated: 10 September 2026

This document covers the quality paths that sit above the normal `quality` SDXL profile. The normal production default remains intentionally conservative and fast enough to use broadly. Expensive or asset-specific techniques must earn promotion through fixed-seed evidence.

## Production baseline

Current default:

```text
profile      quality
resolution   1024 x 1024
steps        36
CFG          6.5
sampler      dpmpp_2m_sde
scheduler    karras
denoise      1.0
passes       1
```

The backend dynamically confirms sampler/scheduler availability against the running ComfyUI `KSampler` inventory and uses quality-biased fallbacks when a preferred choice is unavailable.

## Hero profile

The opt-in `hero` profile is a core-node-only two-pass workflow:

```text
Pass 1
  1024 x 1024
  36 steps
  CFG 6.5
  DPM++ 2M SDE
  Karras
  denoise 1.0

Latent expansion
  1.5x
  bislerp
  1536 x 1536 for square images

Pass 2
  18 steps
  CFG 5.5
  DPM++ 2M SDE
  Karras
  denoise 0.24
```

It does not load an SDXL refiner or external upscaler model. This keeps model residency simpler on the 12 GB RTX 4080 while giving the diffusion model a restrained high-resolution detail pass.

Hero is **not** the universal default. It is intended for high-value final imagery after it proves worthwhile for the relevant subject class.

Run the release comparison:

```powershell
Set-Location C:\GitRepos\evavo-local-image-generator
.\RUN-HERO-QUALITY.ps1
```

The run compares:

```text
quality
hero
detail
euler_reference
legacy_768_reference
```

across the same golden prompts and fixed seeds `1337` and `424242`.

Outputs include:

```text
manifest.json
runtime-evidence.json
quality_metrics.json
human_review.csv
report.html
images\...
```

## Exact reproducibility receipts

Every native ComfyUI queue result now reports:

```text
actual submitted seed
workflow SHA-256
workflow node count
checkpoint name
quality profile and resolved settings
pass count
expected output size
LoRA name/strengths when used
```

When a caller does not supply a seed, EVAVO chooses the same 63-bit random seed class as the underlying adapter but now returns the value to the caller.

For release comparisons, `runtime-snapshot.py` additionally records:

```text
generator repository Git SHA
ComfyUI Git SHA
ComfyUI Python executable/version
PyTorch version
PyTorch CUDA build
CUDA availability and GPU identity
NVIDIA driver and VRAM
ComfyUI /system_stats
custom-node Git SHAs
checkpoint SHA-256
LoRA SHA-256 values
```

Large model hashes are cached using full path + file size + modification time. A changed file invalidates the cache automatically.

## ComfyUI-next evidence

`SETUP-COMFYUI-NEXT.ps1` keeps the existing runtime untouched and creates:

```text
C:\AI\ComfyUI-next
http://127.0.0.1:8189
```

The parallel runtime references model bytes from the existing install through `evavo-current-models.yaml` and records the source root in `evavo-next-runtime.json`.

`RUN-HERO-QUALITY.ps1` and `RUN-LORA-SWEEP.ps1` read that receipt automatically and hash the **actual shared source model bytes** when running against the parallel runtime.

Example:

```powershell
.\SETUP-COMFYUI-NEXT.ps1
.\START-EVAVO-QUALITY-STACK.ps1 -UseNextComfy
.\RUN-HERO-QUALITY.ps1 -ComfyEndpoint http://127.0.0.1:8189
```

Do not replace the working `8188` runtime merely because `8189` is newer. Promote only after fixed-seed image review, stable VRAM behavior, required workflow/custom-node compatibility and the full production gate.

## Technical image diagnostics

`quality-report.py` calculates:

```text
resolution / megapixels
file size
mean luminance
luminance contrast
near-black fraction
near-white fraction
saturation proxy
luminance entropy
local detail energy
seconds per megapixel
```

These are **diagnostics**, not aesthetic quality scores. A noisier image can have more entropy and edge energy while being visibly worse. A clean product render can be excellent with lower entropy. Human review remains authoritative.

## Human image review

Open `report.html` and inspect each comparison at fit-to-screen and 100% zoom. Fill every 1-5 column in `human_review.csv`:

```text
prompt_adherence
composition
detail
anatomy_geometry
materials_texture
lighting_color
artifact_freedom
production_usability
```

Then summarize the evidence:

```powershell
.\FINALIZE-QUALITY-REVIEW.ps1 -Review "C:\path\to\human_review.csv" -Baseline quality
```

The summarizer calculates per-profile human means and exact prompt/seed paired deltas against the baseline. It reports wins/ties/losses but **never changes production defaults automatically**.

For a LoRA sweep use:

```powershell
.\FINALIZE-QUALITY-REVIEW.ps1 -Review "C:\path\to\human_review.csv" -Baseline base
```

## LoRA workflow

LoRA loading is opt-in and isolated. The canonical built-in graph inserts one `LoraLoader` after the checkpoint and routes:

```text
LoRA MODEL -> every KSampler
LoRA CLIP  -> positive and negative CLIP conditioning
```

The same LoRA therefore affects both passes of `hero` consistently.

The backend validates the requested filename against the live ComfyUI LoRA inventory and preflights the resulting graph. Automatic LoRA insertion is refused for arbitrary custom workflows; encode LoRA nodes explicitly in those workflows instead.

Environment controls are available for deliberate global experiments:

```powershell
$env:EVAVO_IMAGE_LORA = "my-lora.safetensors"
$env:EVAVO_IMAGE_LORA_MODEL_STRENGTH = "0.7"
$env:EVAVO_IMAGE_LORA_CLIP_STRENGTH = "0.7"
```

Prefer per-job configuration for production.

### Strength sweep

Use a fixed prompt and seed:

```powershell
.\RUN-LORA-SWEEP.ps1 `
  -Lora "my-lora.safetensors" `
  -Prompt "Your controlled evaluation prompt"
```

Default strengths:

```text
0.0  = true base render; LoRA node is not loaded
0.5
0.7
0.9
```

The same checkpoint, quality profile and seed are retained. The sweep generates runtime/model attestation and the normal side-by-side review package.

Use the **lowest** strength that reliably produces the intended result. Stronger is not automatically better; excessive LoRA strength can distort geometry, texture, color and checkpoint style.

After selecting a strength on the `quality` profile, validate the chosen LoRA/strength again on `hero` only if the asset needs the additional high-resolution pass.

## Wrapper requests

The stable native wrapper accepts the complete quality recipe:

```json
{
  "prompt": "controlled prompt",
  "project_name": "release-candidate",
  "quality_profile": "hero",
  "seed": 1337,
  "lora_name": "my-lora.safetensors",
  "lora_model_strength": 0.7,
  "lora_clip_strength": 0.7,
  "wait": true
}
```

It also accepts explicit sampler/scheduler, first-pass denoise, upscale factor and every second-pass setting.

## Full multimodal release

Run the whole quality stack first:

```powershell
.\START-EVAVO-QUALITY-STACK.ps1
```

Then:

```powershell
.\RUN-FULL-QUALITY-RELEASE.ps1
```

This runs the existing full multimodal gate first:

```text
image profile regressions
native fixed-seed ComfyUI generation
Kokoro golden audio
3D Studio doctor/toolchain/providers/brief/plan/regressions
Atmosphere doctor/media/safety/tests/typecheck/build
```

Only when those pass does it spend GPU time on the full hero A/B review and model/runtime attestation.

To require the live token-gated 3D execution worker:

```powershell
$env:EVAVO_3D_AGENT_EXECUTION_TOKEN = "<operator-managed secret with at least 32 characters>"
.\START-EVAVO-QUALITY-STACK.ps1 -Start3DWorker
.\RUN-FULL-QUALITY-RELEASE.ps1 -Require3DExecution
```

The 3D worker remains candidate-production-only and must report no automatic approval, Git mutation, deployment, publication or client-release authority.

## Release principle

Do not optimize for the most steps, the newest dependency, the highest resolution, the strongest LoRA or the slowest render.

Promote a change when it gives the best **repeatably usable** output across the relevant golden set while preserving:

```text
prompt adherence
visual quality
artifact freedom
reproducibility
runtime stability
VRAM stability
acceptable throughput
downstream compatibility
human approval
```

That is the quality bar for the EVAVO local generation stack.
