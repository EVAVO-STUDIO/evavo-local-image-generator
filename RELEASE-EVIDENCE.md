# EVAVO Local Generation Release Evidence

`RUN-RELEASE.ps1` is the canonical production release-evidence entrypoint for the local generation stack.

It wraps the lower-level quality scripts with a frozen image environment so controlled A/B results cannot silently inherit workstation-level image profile, sampler, LoRA or custom-workflow overrides.

## Canonical release

```powershell
.\RUN-RELEASE.ps1 -Checkpoint "sd_xl_base_1.0.safetensors"
```

For the strongest local stack proof when the HTTP gateway and bounded 3D execution worker are part of the machine configuration:

```powershell
.\RUN-RELEASE.ps1 `
  -Checkpoint "sd_xl_base_1.0.safetensors" `
  -RequireGateway `
  -Require3DExecution
```

The release command does not change image-profile or voice defaults.

## Image environment freeze

During the controlled release only, the process temporarily masks:

```text
EVAVO_IMAGE_QUALITY_PROFILE
EVAVO_IMAGE_WIDTH
EVAVO_IMAGE_HEIGHT
EVAVO_IMAGE_STEPS
EVAVO_IMAGE_CFG
EVAVO_IMAGE_SAMPLER
EVAVO_IMAGE_SCHEDULER
EVAVO_IMAGE_DENOISE
EVAVO_IMAGE_UPSCALE_FACTOR
EVAVO_IMAGE_SECOND_*
EVAVO_IMAGE_LATENT_UPSCALE_METHOD
EVAVO_IMAGE_LORA*
EVAVO_UPGRADE_LEGACY_IMAGE_DEFAULTS
EVAVO_COMFYUI_WORKFLOW
```

Only the names of environment keys that had been present are recorded in `release-policy.json`; their values are not persisted.

The original process environment is restored in `finally`, including on failure.

## Evidence phases

The release has three automated phases:

### 1. Multimodal production gate

The gate verifies the configured local stack, including:

- fixed-seed SDXL quality comparisons
- prompt-quality regressions
- audio-quality regressions
- Kokoro golden speech tests
- Kokoro runtime attestation
- EVAVO 3D Studio doctor/toolchain/provider/regression checks
- optional bounded 3D worker authority check
- 3D runtime attestation
- Atmosphere doctor, real FFmpeg media smoke, typecheck, production safety/tests and build
- Atmosphere runtime attestation
- optional live gateway image round trip

### 2. Hero image A/B evidence

The hero release suite compares:

```text
quality
hero
detail
euler_reference
legacy_768_reference
```

against the same versioned golden prompts and fixed seeds.

It produces:

- image outputs
- benchmark manifest
- checkpoint/runtime evidence
- technical image diagnostics
- local HTML comparison report
- `human_review.csv`

### 3. Integrity seal

The release directory is hashed by `release-evidence.py`.

`release-manifest.json` records:

- every evidence file path
- byte size
- SHA-256
- selected JSON status fields
- one SHA-256 fingerprint over the ordered evidence set

Modified, missing, extra or path-escaping evidence files fail later verification.

## Release directory

Default location:

```text
.evavo/quality-results/full-release/<timestamp>/
```

Typical structure:

```text
full-release/<timestamp>/
  gate/
    release-gate.json
    kokoro-runtime.json
    3d-runtime.json
    atmosphere-runtime.json
    comfyui/...
    kokoro/...
    gateway/...              # when required
    *.log
  hero/
    <benchmark-run>/
      manifest.json
      runtime-evidence.json
      quality_metrics.json
      report.html
      human_review.csv
      images/...
  release-summary.json
  release-policy.json
  release-manifest.json
```

All of this is under `.evavo/` and is ignored by Git.

## Verify an untouched release

```powershell
.\VERIFY-FULL-RELEASE.ps1 `
  -ReleaseRoot ".\.evavo\quality-results\full-release\<timestamp>"
```

This checks every file against the current integrity manifest.

## Human review intentionally changes evidence

The first seal proves the automated evidence exactly as it existed before human scoring.

When you fill in the image and Kokoro `human_review.csv` files, the original integrity seal should fail. That is expected because the evidence changed.

Do not manually rebuild the manifest immediately after editing. Finalize the reviews first.

## Finalize and reseal

After every image and speech score is complete:

```powershell
.\FINALIZE-FULL-RELEASE.ps1 `
  -ReleaseRoot ".\.evavo\quality-results\full-release\<timestamp>"
```

The finalizer:

1. validates every image 1–5 score;
2. writes the image human-review summary;
3. validates every Kokoro listening score;
4. writes the voice evidence ranking;
5. writes `finalization.json` with review/summary hashes;
6. records `automaticPromotion=false`;
7. reseals the complete directory;
8. verifies the new seal immediately.

This creates a final human-reviewed evidence bundle without silently changing production defaults.

## Promote only after evidence

An image profile or voice should be promoted only after:

- automated gates pass;
- runtime/model evidence is complete;
- image dimensions and technical diagnostics are correct;
- fixed-seed visual review is complete;
- listening review is complete where speech is relevant;
- the final release bundle verifies successfully.

A profile should not win merely because it has more steps or higher resolution. A voice should not win because one sentence sounds impressive.

## Parallel ComfyUI migration

When validating `C:\AI\ComfyUI-next` on port 8189, point the canonical release at that runtime and its root:

```powershell
.\RUN-RELEASE.ps1 `
  -Checkpoint "sd_xl_base_1.0.safetensors" `
  -ComfyEndpoint "http://127.0.0.1:8189" `
  -ComfyRoot "C:\AI\ComfyUI-next"
```

The runtime evidence follows the parallel-install receipt so shared checkpoint/LoRA bytes are hashed from their real source model store.

Do not replace the working 8188 runtime solely because 8189 starts successfully. Promote only after the same controlled release evidence is better or equivalent and required custom nodes pass.

## Related commands

```text
RUN-RELEASE.ps1                 canonical frozen full release
RUN-PRODUCTION-QUALITY.ps1      lower-level multimodal gate
RUN-HERO-QUALITY.ps1            fixed-seed image A/B package
RUN-KOKORO-VOICE-COMPARISON.ps1 controlled speech voice comparison
RUN-LORA-SWEEP.ps1              isolated LoRA strength comparison
FINALIZE-FULL-RELEASE.ps1       validate human review + reseal
VERIFY-FULL-RELEASE.ps1         verify tamper-evident bundle
run-batch-plan.py               frozen per-item image batch plans
batch-resume.py                 safe non-duplicating batch recovery
```
