# Kokoro Production Quality

Kokoro is treated as a local speech renderer with a controlled release process, not as a success-if-bytes-exist endpoint.

## Baseline

Default endpoint:

```text
http://127.0.0.1:8880
```

Use WAV for generation masters and QC. Convert to delivery codecs later when a downstream target requires them.

The gateway uses Kokoro only as a speech fallback when the broader EVAVO Audio Studio provider is unavailable.

## Golden corpus

Controlled speech text lives in:

```text
config/kokoro-golden-texts-v1.json
```

It covers:

- neutral narration
- dates, time and currency
- expressive punctuation
- technical wording and dimensions
- proper nouns / Australian place names / EVAVO tooling names

Do not silently rewrite an established corpus after release evidence exists. Add a new version.

## Technical quality gate

Run:

```powershell
python kokoro-quality-test.py --endpoint http://127.0.0.1:8880
```

Each WAV is checked for:

- duration
- sample rate
- mono/stereo channel sanity
- peak and RMS level
- clipped samples
- DC offset
- leading/trailing silence
- effective words per minute
- input and output SHA-256

The checks intentionally catch obvious technical failures and truncation. They do not measure naturalness, emotion or pronunciation quality.

## Voice comparison

Run the same five texts through all candidate voices:

```powershell
.\RUN-KOKORO-VOICE-COMPARISON.ps1
```

Optional example:

```powershell
.\RUN-KOKORO-VOICE-COMPARISON.ps1 `
  -Voices "af_heart,af_bella,bf_emma" `
  -Speed 0.98
```

The command writes a `human_review.csv`. Score every sample from 1 to 5 for:

- naturalness
- pronunciation
- pacing
- emotional fit
- artifact freedom
- production usability

A production voice should perform consistently across the corpus, not just sound impressive on one sentence.

## Finalize listening evidence

After filling every score:

```powershell
.\FINALIZE-KOKORO-REVIEW.ps1 -ReviewCsv "<path-to-human_review.csv>"
```

The summary ranks the evidence by production usability, artifact freedom, pronunciation and overall average. It never changes `EVAVO_KOKORO_VOICE` automatically.

## Gateway receipt

For WAV requests, the Kokoro gateway provider now returns:

```text
inputSha256
sha256
voice
speed
format
metrics
technicalQc
```

A WAV that fails the conservative technical QC is not accepted as a successful provider artifact.

## Speed

Keep `1.0` as the comparison baseline. Evaluate nearby values such as `0.92`, `0.98`, `1.04` or `1.08` only after choosing a voice. Compare one variable at a time.

Avoid using speed to hide pronunciation or prosody problems.

## Release integration

`RUN-PRODUCTION-QUALITY.ps1` uses:

- quick: neutral
- standard: neutral + numbers
- full: all five golden texts

For the strongest local release proof:

```powershell
.\RUN-FULL-QUALITY-RELEASE.ps1 -RequireGateway -Require3DExecution
```

That still requires human image and listening review before changing promoted image profiles or voice defaults.
