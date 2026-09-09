"""Deterministic prompt compilation, linting and fingerprinting.

The linter is intentionally conservative: it catches structural mistakes that
can waste GPU time, but it never claims to score aesthetics or predict image
quality. Human visual review remains authoritative.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

_WS_RE = re.compile(r"\s+")
_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'_-]*")

QUALITY_BOILERPLATE = {
    "masterpiece", "best quality", "8k", "16k", "ultra detailed",
    "highly detailed", "award winning", "trending on artstation",
}

CONTRADICTION_GROUPS: tuple[tuple[str, ...], ...] = (
    ("front-on", "top-down", "isometric"),
    ("eye-level", "bird's-eye", "overhead view"),
    ("photorealistic", "pixel art", "engraved linework"),
    ("black-and-white", "vivid saturated color"),
    ("soft diffused light", "hard direct flash"),
)

ORDERED_FIELDS = (
    "subject",
    "action",
    "composition",
    "camera",
    "environment",
    "lighting",
    "materials",
    "period",
    "style",
    "constraints",
)


@dataclass(frozen=True)
class PromptIssue:
    severity: str
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def normalize_prompt(text: Any) -> str:
    if text is None:
        return ""
    return _WS_RE.sub(" ", str(text)).strip(" ,;\t\r\n")


def prompt_sha256(prompt: str, negative_prompt: str = "") -> str:
    payload = {
        "prompt": normalize_prompt(prompt),
        "negative_prompt": normalize_prompt(negative_prompt),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _phrase_present(text: str, phrase: str) -> bool:
    return phrase.lower() in text.lower()


def _repeated_clauses(text: str) -> list[str]:
    clauses = [normalize_prompt(value).lower() for value in re.split(r"[,;.]", text)]
    clauses = [value for value in clauses if len(value) >= 8]
    counts: dict[str, int] = {}
    for clause in clauses:
        counts[clause] = counts.get(clause, 0) + 1
    return sorted(value for value, count in counts.items() if count > 1)


def lint_prompt(prompt: str, negative_prompt: str = "") -> dict[str, Any]:
    positive = normalize_prompt(prompt)
    negative = normalize_prompt(negative_prompt)
    issues: list[PromptIssue] = []

    if not positive:
        issues.append(PromptIssue("error", "EMPTY_PROMPT", "Positive prompt is empty."))
    if len(positive) > 4000:
        issues.append(PromptIssue("warning", "VERY_LONG_PROMPT", "Prompt exceeds 4000 characters; important direction may be diluted."))

    lower = positive.lower()
    boilerplate = sorted(phrase for phrase in QUALITY_BOILERPLATE if phrase in lower)
    if len(boilerplate) >= 3:
        issues.append(PromptIssue(
            "warning",
            "QUALITY_KEYWORD_SOUP",
            "Multiple generic quality tokens are present; prefer concrete subject, camera, light, material and composition direction.",
        ))

    for group in CONTRADICTION_GROUPS:
        present = [phrase for phrase in group if _phrase_present(positive, phrase)]
        if len(present) > 1:
            issues.append(PromptIssue(
                "error",
                "CONTRADICTORY_DIRECTION",
                "Conflicting positive-prompt direction: " + ", ".join(present),
            ))

    duplicates = _repeated_clauses(positive)
    if duplicates:
        issues.append(PromptIssue(
            "warning",
            "REPEATED_CLAUSE",
            "Repeated prompt clause(s): " + "; ".join(duplicates[:3]),
        ))

    if negative:
        overlap = []
        positive_terms = {word.lower() for word in _WORD_RE.findall(positive) if len(word) >= 5}
        negative_terms = {word.lower() for word in _WORD_RE.findall(negative) if len(word) >= 5}
        for term in sorted(positive_terms & negative_terms):
            if term not in {"detail", "lighting", "texture", "realistic"}:
                overlap.append(term)
        if len(overlap) >= 4:
            issues.append(PromptIssue(
                "warning",
                "POSITIVE_NEGATIVE_OVERLAP",
                "Positive and negative prompts share several substantive terms: " + ", ".join(overlap[:8]),
            ))

    concrete_markers = (
        "camera", "angle", "front", "three-quarter", "eye-level", "lens",
        "light", "shadow", "surface", "material", "foreground", "midground",
        "background", "composition", "framing", "perspective",
    )
    if positive and not any(marker in lower for marker in concrete_markers):
        issues.append(PromptIssue(
            "warning",
            "LOW_VISUAL_SPECIFICITY",
            "Prompt has little explicit camera/composition/lighting/material direction.",
        ))

    return {
        "ok": not any(issue.severity == "error" for issue in issues),
        "prompt": positive,
        "negative_prompt": negative,
        "prompt_sha256": prompt_sha256(positive, negative),
        "issues": [issue.as_dict() for issue in issues],
        "error_count": sum(issue.severity == "error" for issue in issues),
        "warning_count": sum(issue.severity == "warning" for issue in issues),
    }


def _parts(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        normalized = normalize_prompt(value)
        return [normalized] if normalized else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [item for raw in value if (item := normalize_prompt(raw))]
    normalized = normalize_prompt(value)
    return [normalized] if normalized else []


def compile_prompt(spec: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(spec, Mapping):
        raise ValueError("prompt specification must be an object")
    positive_parts: list[str] = []
    for field in ORDERED_FIELDS:
        positive_parts.extend(_parts(spec.get(field)))
    positive_parts.extend(_parts(spec.get("positive")))
    negative_parts = _parts(spec.get("negative"))

    prompt = ", ".join(dict.fromkeys(positive_parts))
    negative = ", ".join(dict.fromkeys(negative_parts))
    result = lint_prompt(prompt, negative)
    result["source_fields"] = [field for field in ORDERED_FIELDS if _parts(spec.get(field))]
    return result


def load_prompt_corpus(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    try:
        raw = source.read_bytes()
        payload = json.loads(raw.decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid prompt corpus {source}: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("prompts"), dict):
        raise ValueError("prompt corpus must contain a prompts object")
    prompts: dict[str, Any] = {}
    for prompt_id, value in payload["prompts"].items():
        if not isinstance(prompt_id, str) or not prompt_id or not isinstance(value, dict):
            raise ValueError("prompt corpus entries must be named objects")
        lint = lint_prompt(str(value.get("prompt", "")), str(value.get("negative", "")))
        if not lint["ok"]:
            raise ValueError(f"prompt corpus entry {prompt_id!r} has lint errors: {lint['issues']}")
        prompts[prompt_id] = {**value, "lint": lint}
    return {
        "schema_version": payload.get("schema_version"),
        "prompt_set_version": payload.get("prompt_set_version"),
        "source": str(source),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "prompts": prompts,
    }
