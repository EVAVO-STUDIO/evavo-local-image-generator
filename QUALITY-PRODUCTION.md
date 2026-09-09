# EVAVO Local Generation — Production Quality Runbook

Updated: 10 September 2026

This document is the operational source of truth for quality-first local generation across:

- ComfyUI / SDXL
- Kokoro-FastAPI
- EVAVO Atmosphere Studio

The goal is not to maximize a single quality keyword or step count. The goal is to keep the whole local stack reproducible, measurable, recoverable and visually/audibly better on the actual RTX 4080 machine.

## 1. Canonical SDXL quality defaults

EVAVO package-level ComfyUI callers now resolve through `QualityComfyUIBackend`.

Default `quality` profile:

```text
resolution   1024 x 1024
steps        36
CFG          6.5
sampler      dpmpp_2m_sde
scheduler    karras
denoise      1.0
batch size   1 at the orchestration layer
```

Additional profiles:

```text
draft                 1024x1024 / 26 / 6.0 / dpmpp_2m_sde / karras
detail                1024x1024 / 42 / 6.0 / dpmpp_3m_sde / karras
euler_reference       1024x1024 / 30 / 6.5 / euler / karras
legacy_768_reference   768x768  / 30 / 8.0 / euler / normal
```

The `legacy_768_reference` profile exists for A/B evidence only. Do not promote it back to the production default because one seed happens to look better.

### Legacy caller upgrade behavior

Older EVAVO callers historically supplied `steps=24` and `cfg_scale=7.0` even when the user did not deliberately choose those settings. The quality resolver treats that exact legacy pair as an implicit old default and upgrades it to the production quality profile.

To deliberately request 24 / 7 for an experiment, use:

```text
quality_profile=custom
```

or disable the compatibility upgrade:

```powershell
$env:EVAVO_UPGRADE_LEGACY_IMAGE_DEFAULTS = "0"
```

## 2. Environment controls

The quality profile can be changed without editing source:

```powershell
$env:EVAVO_IMAGE_QUALITY_PROFILE = "quality"
$env:EVAVO_IMAGE_WIDTH = "1024"
$env:EVAVO_IMAGE_HEIGHT = "1024"
$env:EVAVO_IMAGE_STEPS = "36"
$env:EVAVO_IMAGE_CFG = "6.5"
$env:EVAVO_IMAGE_SAMPLER = "dpmpp_2m_sde"
$env:EVAVO_IMAGE_SCHEDULER = "karras"
$env:EVAVO_IMAGE_DENOISE = "1.0"
$env:EVAVO_BATCH_CONCURRENCY = "1"
```

The backend queries the running ComfyUI `KSampler` inventory. If a preferred sampler/scheduler is not present it selects the best available quality fallback instead of failing blindly.

## 3. GPU policy for the RTX 4080 12 GB

Quality-first production policy:

- keep final SDXL generation at 1024-class resolution
- use one heavy image job at a time
- queue work instead of increasing latent batch size
- run ComfyUI with normal smart memory management first
- disable preview generation when it is not needed
- reserve about 1 GB VRAM for Windows/display headroom
- do not enable `--lowvram` unless a real workflow cannot complete otherwise
- do not benchmark old and new ComfyUI runtimes while both are actively rendering
- close unrelated GPU-heavy applications before a benchmark

The batch CLI therefore defaults to concurrency `1`.

## 4. Current runtime and safe migration

The existing working installation is deliberately preserved:

```text
C:\AI\ComfyUI
http://127.0.0.1:8188
```

Reported current environment:

```text
PyTorch 2.7.1+cu118
CUDA build 11.8
```

Current ComfyUI NVIDIA installation guidance has moved to newer PyTorch/CUDA packages. Do not overwrite the only working environment to chase a version number.

Prepare a parallel runtime instead:

```powershell
Set-Location C:\GitRepos\evavo-local-image-generator
.\SETUP-COMFYUI-NEXT.ps1
```

Default parallel environment:

```text
C:\AI\ComfyUI-next
Python 3.12
PyTorch CUDA 13.0 wheels
http://127.0.0.1:8189
```

Python 3.12 is the default here because custom-node compatibility matters more than having the newest interpreter. The script also accepts `-PythonVersion 3.13` when all required nodes are known to support it.

The migration script:

1. never modifies `C:\AI\ComfyUI`
2. creates or safely updates `C:\AI\ComfyUI-next`
3. creates its own `.venv`
4. installs the current NVIDIA PyTorch CUDA 13.0 package line
5. installs ComfyUI requirements
6. references the current model library through an external model-path config
7. probes `torch.cuda.is_available()` and the actual GPU
8. creates `START-EVAVO-COMFYUI-NEXT.ps1`
9. writes `evavo-next-runtime.json`

Custom nodes are **not** copied by default because they are the largest compatibility risk. Only use:

```powershell
.\SETUP-COMFYUI-NEXT.ps1 -InstallCurrentCustomNodes
```

after the clean core runtime has generated correctly.

## 5. Start the complete stack

Current ComfyUI:

```powershell
.\START-EVAVO-QUALITY-STACK.ps1
```

Parallel ComfyUI-next:

```powershell
.\START-EVAVO-QUALITY-STACK.ps1 -UseNextComfy
```

The stack launcher verifies or starts:

```text
ComfyUI            8188 or 8189
Kokoro-FastAPI     8880
Atmosphere Studio  3000
```

Logs are written outside Git under:

```text
C:\AI\evavo-generation-results\service-logs\<timestamp>
```

## 6. Fixed-seed ComfyUI benchmark

Do not compare settings from memory. Compare the same prompts and seeds.

Normal release comparison:

```powershell
python .\quality-benchmark.py \
  --endpoint http://127.0.0.1:8188 \
  --profiles quality,euler_reference,legacy_768_reference \
  --prompts product,portrait,landscape,interior \
  --seeds 1337
```

Full comparison:

```powershell
python .\quality-benchmark.py \
  --endpoint http://127.0.0.1:8188 \
  --profiles quality,detail,euler_reference,legacy_768_reference \
  --prompts product,portrait,landscape,interior,game_art \
  --seeds 1337,424242
```

The benchmark is sequential by design and records:

- native ComfyUI health
- available samplers/schedulers
- profile actually applied
- seed
- generation time
- downloaded output
- dimensions
- bytes
- SHA-256
- failures

Results live under:

```text
.evavo\quality-results\...
```

and are excluded from ordinary Git.

## 7. Promote ComfyUI-next only with evidence

Benchmark the current runtime first:

```powershell
.\START-EVAVO-QUALITY-STACK.ps1
python .\quality-benchmark.py --endpoint http://127.0.0.1:8188 --profiles quality,euler_reference --prompts product,portrait,landscape,interior --seeds 1337,424242
```

Then stop the old heavy generation workload, start the parallel runtime and repeat the same test:

```powershell
.\START-EVAVO-QUALITY-STACK.ps1 -UseNextComfy
python .\quality-benchmark.py --endpoint http://127.0.0.1:8189 --profiles quality,euler_reference --prompts product,portrait,landscape,interior --seeds 1337,424242
```

Do not promote the new runtime merely because it is newer.

Promotion criteria:

- core generation completes with zero fatal errors
- required checkpoints are discovered correctly
- required custom workflows preflight correctly
- required custom nodes load correctly
- same-seed images are at least as good visually
- no systematic new anatomy/geometry/color defect appears
- median generation time is acceptable
- VRAM behavior is stable
- repeated jobs do not leak memory or force progressive offloading
- the full EVAVO production quality gate passes

Only then change the canonical endpoint from 8188 to 8189 or replace the old environment.

## 8. Human image review

Technical success is necessary but not enough.

Review each candidate at fit-to-screen and 100% zoom. Score 1–5 for:

```text
prompt adherence
composition
detail
anatomy / geometry
materials / texture
lighting / color
artifact freedom
overall production usability
```

A profile should not be promoted based on one hero image. Use the whole golden prompt set and multiple fixed seeds.

Common failure patterns to inspect:

- waxy or over-crunchy skin
- malformed fingers/eyes
- duplicated small objects
- melted product edges
- broken architectural verticals
- smeared fine foliage
- artificial saturation
- haloing from excessive CFG
- incoherent text-like marks
- modern details leaking into historical art

## 9. Prompt construction

Prefer concrete visual direction:

```text
subject
→ state/action
→ composition
→ environment
→ lighting
→ camera/perspective
→ material details
→ style/medium
→ constraints
```

Avoid using keyword soup as a substitute for art direction.

Poor:

```text
masterpiece, best quality, 8k, insane details, award winning, perfect, beautiful
```

Better:

```text
Minimal black anodized aluminium desk speaker on a matte charcoal surface,
three-quarter front angle, large diffused key light with narrow edge light,
precise machined edges, fine metal grain, accurate geometry,
natural contact shadow, restrained commercial product photography
```

Keep negative prompts short and failure-specific.

## 10. LoRA policy

New LoRAs must be evaluated in isolation with a fixed checkpoint, prompt, seed and sampler.

Recommended first test strengths:

```text
0.00
0.50
0.70
0.90
```

Track:

- filename
- SHA-256
- source
- license
- base model compatibility
- trigger words
- tested strength range

Do not commit model binaries to ordinary Git.

## 11. Kokoro quality path

The production Kokoro client now uses the OpenAI-compatible local API at:

```text
http://127.0.0.1:8880
```

The client supports:

- voice inventory
- voice validation
- WAV / FLAC / MP3 / Opus / AAC / PCM output requests
- output-signature validation
- atomic file writes
- validated speech speed
- explicit failures for empty/invalid audio

Use WAV for master QC.

Golden audio test:

```powershell
python .\kokoro-quality-test.py --endpoint http://127.0.0.1:8880
```

The test covers:

```text
neutral prose
numbers / dates / currency
expressive dialogue
```

and records WAV duration, sample rate, peak, RMS and clipping where 16-bit PCM analysis is possible.

Technical audio quality does not replace listening review. Score:

```text
pronunciation
prosody
naturalness
pace
emotion where relevant
artifact freedom
overall usability
```

Keep speed near `1.0` unless testing proves another value is better for the selected voice.

## 12. Atmosphere Studio integration

Canonical repository:

```text
C:\GitRepos\atmosphere-studio
EVAVO-STUDIO/atmosphere-studio
```

Atmosphere Studio already owns the correct downstream responsibilities:

- approved/generated source imagery
- masks and depth-related assets
- rain/fog/splash/lightning/weather layers
- wet-surface and reflection behavior
- specialty effects
- layered audio/mastering
- deterministic visual variants
- resumable long-form video segments
- final audio mux
- review and approval
- technical/perceptual QC
- checksummed delivery

Do **not** add a universal `steps >= 30` rule inside Atmosphere workflow registration. Some future models legitimately use very different sampling budgets. Image-model sampling quality belongs in the generator/workflow profile; Atmosphere should enforce versioned workflow identity, source-asset approval and output QC.

## 13. Atmosphere validation

Quick:

```powershell
Set-Location C:\GitRepos\atmosphere-studio
npm run doctor
```

Standard:

```powershell
npm run doctor
npm run smoke:media
npm run typecheck
```

Full release gate:

```powershell
npm run doctor
npm run smoke:media -- --keep
npm run safety:production
npm run test:production
npm run typecheck
npm run build
```

Do not begin a multi-hour render while `smoke:media` or machine doctor is failing.

## 14. One-command production quality gate

From this repository:

```powershell
.\RUN-PRODUCTION-QUALITY.ps1 -Mode quick
.\RUN-PRODUCTION-QUALITY.ps1 -Mode standard
.\RUN-PRODUCTION-QUALITY.ps1 -Mode full
```

Against ComfyUI-next:

```powershell
.\RUN-PRODUCTION-QUALITY.ps1 -Mode standard -ComfyEndpoint http://127.0.0.1:8189
```

The gate runs:

1. offline quality-profile regressions
2. native fixed-seed ComfyUI comparisons
3. Kokoro golden audio generation/QC
4. Atmosphere machine doctor
5. media smoke/typecheck in standard mode
6. production safety/tests/build in full mode

It writes a durable release result under:

```text
.evavo\quality-results\release-gates\<timestamp>\release-gate.json
```

A non-zero exit code means the stack is not release-ready.

## 15. Repository validation after pulling these changes

Run the repository's existing verification suite first, then the new quality regressions:

```powershell
Set-Location C:\GitRepos\evavo-local-image-generator
.\UPDATE-AND-VERIFY-EVAVO.ps1
python .\test_quality_profiles.py
python .\quality-benchmark.py --dry-run
```

Then start the actual services and run:

```powershell
.\START-EVAVO-QUALITY-STACK.ps1
.\RUN-PRODUCTION-QUALITY.ps1 -Mode standard
```

## 16. Model/version reproducibility

A reproducible generation record should contain at least:

```text
checkpoint filename + SHA-256
VAE
LoRA filenames + hashes + strengths
workflow identity/version/checksum
prompt
negative prompt
seed
width / height
steps
CFG
sampler
scheduler
denoise
ComfyUI commit
Python version
PyTorch version
PyTorch CUDA build
custom-node versions
output SHA-256
```

Model weights and generated masters stay outside normal Git. Configuration, manifests, scripts and hashes belong in Git.

## 17. What “best quality” means in EVAVO

Best quality is the highest **repeatably usable** result, not the most expensive render.

A change is an upgrade only if it improves the real production stack across:

- visual/audio quality
- prompt/script adherence
- artifact rate
- consistency
- reproducibility
- machine stability
- recovery/retry behavior
- downstream Atmosphere compatibility
- measured throughput

If 42 steps looks indistinguishable from 36 across the golden set, keep 36. If a new PyTorch build is faster but breaks a required custom node, do not promote it. If a new checkpoint looks spectacular on portraits but breaks historical interiors, profile it by use case rather than making it universal.

That is the quality policy for this stack going forward.
