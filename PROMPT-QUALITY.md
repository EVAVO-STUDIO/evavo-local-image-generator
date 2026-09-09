# EVAVO Prompt Quality

This repository treats prompt quality as a **versioned production input**, not an informal string pasted into a sampler.

The goal is not to make prompts longer. The goal is to make them clearer, testable and reproducible.

## Production order

A useful image prompt should establish the important visual facts in roughly this order:

1. subject and action
2. composition and camera
3. environment
4. lighting
5. materials and period detail
6. style
7. hard constraints
8. negative exclusions

Prefer concrete direction such as `fixed front-on camera`, `large diffused key light`, `wet black stone`, `straight verticals` and `broad clear gameplay lane` over generic tokens such as `masterpiece`, `best quality`, `8k`, `ultra detailed`.

## Lint one prompt

```powershell
python prompt-quality.py lint `
  --prompt "black anodized desk speaker, three-quarter front angle, large diffused key light, matte charcoal surface" `
  --negative "warped geometry, duplicate object, text, watermark"
```

The command returns:

- normalized positive and negative prompts
- SHA-256 of the exact prompt pair
- structural errors
- non-blocking warnings

It does **not** produce an aesthetic score.

Use `--strict-warnings` only for controlled prompt libraries. Normal creative work may reasonably contain warnings that require human judgment.

## Compile a structured prompt

Example:

```powershell
python prompt-quality.py compile --spec .\examples\prompt-spec-1871-chandlery.json
```

Supported positive fields are emitted deterministically in this order:

```text
subject
action
composition
camera
environment
lighting
materials
period
style
constraints
positive
```

`negative` is compiled separately.

Repeated entries are removed while preserving first occurrence. This makes generated prompt text stable enough to fingerprint and compare.

## What the linter catches

The linter deliberately focuses on problems that can waste a render:

- empty prompt
- very long prompts likely to dilute important direction
- generic quality-keyword soup
- exact repeated clauses
- several classes of contradictory positive direction, such as `front-on` + `isometric`
- substantial positive/negative term overlap
- very low camera/composition/lighting/material specificity

The contradiction table is conservative and should remain small. Do not turn it into a giant artistic rules engine.

## Golden prompt corpus

The fixed-seed quality benchmark reads:

```text
config/quality-golden-prompts-v1.json
```

Do not silently rewrite that file after it has been used for promotion evidence. If the benchmark corpus materially changes, add a new version such as:

```text
quality-golden-prompts-v2.json
```

Every benchmark manifest records:

- prompt-set version
- corpus file SHA-256
- per-prompt SHA-256
- review focus for each prompt

That makes a future A/B comparison distinguish a model/runtime/profile change from a prompt change.

Validate the corpus without rendering:

```powershell
python prompt-quality.py corpus
python quality-benchmark.py --dry-run --profiles quality,hero --prompts product,portrait --seeds 1337
```

## Negative prompts

Negative prompts should target likely failure modes for the requested image, not become a universal wall of generic tokens.

Good examples:

```text
warped walls, duplicate doors, modern fixtures, fisheye, text, watermark
```

```text
malformed hands, crossed eyes, duplicate face, waxy skin, watermark
```

Avoid automatically adding exclusions that directly conflict with the desired style or subject.

## Historical and game-art work

For period work, explicitly state:

- year or era
- camera/gameplay readability requirements
- materials
- architecture/interior type
- allowed lighting technology
- modern items that must not leak into the scene

For side-stage or front-on game backgrounds, describe the clear interaction lane and silhouette hierarchy directly rather than relying on phrases such as `game background`.

## Relationship to quality profiles

Prompt quality and sampler quality are separate variables.

When comparing `quality`, `hero`, Euler or LoRA settings, keep the prompt corpus and seed fixed. When evaluating a prompt rewrite, keep the runtime/checkpoint/profile/seed fixed.

Do not change both sides of an A/B test at once.
