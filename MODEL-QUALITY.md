# EVAVO Local Model Quality

Model names are not quality evidence. EVAVO treats checkpoint selection as a controlled production decision.

## 1. Inventory what is actually installed

```powershell
.\RUN-MODEL-INVENTORY.ps1
```

This writes local evidence under `.evavo/model-inventory.json` and reports:

- model locations and sizes
- checkpoint / LoRA / VAE / upscaler categories
- bounded SafeTensors metadata without loading tensors
- conservative architecture hints from filename/metadata
- whether checkpoint/LoRA names are visible to the running ComfyUI instance
- possible duplicate files

For exact duplicate/provenance evidence:

```powershell
.\RUN-MODEL-INVENTORY.ps1 -HashModels
```

Full hashing intentionally remains opt-in because reading every multi-GB model can take substantial disk time. Release-oriented benchmark tools hash only the models they actually used.

## 2. Architecture hints are not certification

`model-inventory.py` may report hints such as:

```text
sdxl
sd15
flux
sd3
hunyuan
lora
```

These come from SafeTensors metadata and filenames. They are useful for triage only.

Do **not** infer from a filename that a checkpoint is interchangeable with SDXL Base.

For example, an SD 1.x checkpoint and an SDXL checkpoint may both load through ComfyUI's generic checkpoint node, but they were trained around different native resolutions and conditioning architectures. Comparing both under a single 1024 SDXL recipe can answer a stress-test question, but it is not necessarily a fair architecture-specific quality comparison.

## 3. Compare checkpoints within a compatible family first

Use an explicit checkpoint list:

```powershell
.\RUN-CHECKPOINT-SWEEP.ps1 `
  -Checkpoints "sd_xl_base_1.0.safetensors,my-sdxl-checkpoint.safetensors"
```

The sweep:

1. requires 2–12 explicitly named checkpoints
2. resolves them against the **live ComfyUI checkpoint inventory** before rendering
3. rejects ambiguous basename matches
4. uses the versioned EVAVO golden prompt corpus
5. uses fixed seeds
6. uses one controlled sampling profile for every checkpoint
7. runs with ambient image/LoRA/workflow overrides disabled
8. renders sequentially
9. builds the same side-by-side diagnostics + human review CSV used by profile comparisons
10. hashes every checkpoint used in the sweep through `runtime-snapshot.py`
11. never promotes a checkpoint automatically

Default comparison set:

```text
sampling profile  quality
prompts           product, portrait, interior, game_art
seed              1337
```

For stronger evidence:

```powershell
.\RUN-CHECKPOINT-SWEEP.ps1 `
  -Checkpoints "model-a.safetensors,model-b.safetensors,model-c.safetensors" `
  -Prompts "product,portrait,landscape,interior,game_art" `
  -Seeds "1337,424242"
```

That is 10 renders per checkpoint.

## 4. Use `quality` before `hero` when screening models

Screen checkpoint quality at the normal 1024 `quality` profile first.

Reasons:

- cheaper comparison
- fewer variables
- easier to identify model-specific defects
- avoids rewarding a weaker base model merely because the second pass hides some defects

Once a checkpoint has passed base screening, compare its hero output separately:

```powershell
.\RUN-CHECKPOINT-SWEEP.ps1 `
  -Checkpoints "model-a.safetensors,model-b.safetensors" `
  -Profile hero `
  -Seeds "1337,424242"
```

## 5. Cross-architecture comparisons need architecture-specific workflows

If inventory suggests a model is SD 1.x, FLUX, SD3, Hunyuan or another family, do not assume the canonical SDXL profile is the best way to use it.

Preferred sequence:

```text
identify architecture
-> identify native/recommended workflow
-> validate required ComfyUI nodes
-> create a versioned workflow/profile
-> fixed-seed benchmark inside that architecture
-> compare production usefulness against the SDXL baseline
```

A model wins only if its **best validated production workflow** is better for the target work, not because it survives an inappropriate SDXL recipe.

## 6. Human model review

Use the generated `human_review.csv` and score every candidate on the same eight dimensions:

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

For historical/game art, additionally use the `review_focus` evidence in the golden corpus for period leakage, fixed-camera readability and style coherence.

Do not pick a model from one portrait or one product image.

## 7. Combine model quality with measured GPU cost

After narrowing checkpoints, use:

```powershell
.\RUN-GPU-QUALITY-BENCHMARK.ps1
```

This measures profile cost on the real GPU while fixed-seed image review measures output usefulness.

Keep the distinction clear:

```text
model/checkpoint choice      visual behavior and training prior
sampling profile             inference quality/cost policy
LoRA                         controlled specialization
GPU/runtime                  speed, VRAM, stability
prompt/workflow              composition and conditioning contract
human review                 production quality decision
```

Changing several at once makes the result impossible to diagnose.

## 8. Promotion criteria

A new checkpoint should become a production default only when:

- its architecture/workflow is understood
- the exact model bytes are hashed
- fixed-seed results are equal or better across the relevant golden set
- no systematic new anatomy, geometry, period, text-like or material defect appears
- prompt adherence is acceptable
- its real RTX GPU cost is acceptable
- required LoRAs remain compatible or are re-evaluated
- downstream Atmosphere / game-art requirements remain intact
- the selected runtime remains stable across repeated jobs

No inventory, benchmark or report script in this repository changes the production checkpoint automatically.
