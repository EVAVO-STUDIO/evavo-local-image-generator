"""Offline tests for EVAVO prompt compilation and quality linting."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from evavo_local_image_generator.prompt_quality import (
    compile_prompt,
    lint_prompt,
    load_prompt_corpus,
    prompt_sha256,
)


ROOT = Path(__file__).resolve().parent


class PromptQualityTests(unittest.TestCase):
    def test_compile_prompt_is_deterministic_and_ordered(self):
        spec = {
            "style": ["restrained engraved game art", "dense hatching"],
            "subject": "1871 riverfront chandlery",
            "lighting": "rain-darkened daylight",
            "camera": "fixed front-on camera",
            "constraints": ["clear lower-third gameplay lane", "no modern signage"],
            "negative": ["isometric view", "electric lights", "watermark"],
        }
        first = compile_prompt(spec)
        second = compile_prompt(spec)
        self.assertTrue(first["ok"])
        self.assertEqual(first["prompt"], second["prompt"])
        self.assertEqual(first["prompt_sha256"], second["prompt_sha256"])
        self.assertTrue(first["prompt"].startswith("1871 riverfront chandlery, fixed front-on camera"))
        self.assertIn("rain-darkened daylight", first["prompt"])
        self.assertEqual(first["negative_prompt"], "isometric view, electric lights, watermark")
        self.assertNotIn("quality_score", first)
        self.assertNotIn("aesthetic_score", first)

    def test_prompt_fingerprint_changes_when_negative_changes(self):
        base = prompt_sha256("front-on portrait, soft window light", "watermark")
        changed = prompt_sha256("front-on portrait, soft window light", "watermark, blurry")
        self.assertNotEqual(base, changed)

    def test_linter_rejects_conflicting_camera_direction(self):
        result = lint_prompt(
            "Victorian room, fixed front-on camera, isometric view, soft window light",
            "watermark",
        )
        self.assertFalse(result["ok"])
        codes = {item["code"] for item in result["issues"]}
        self.assertIn("CONTRADICTORY_DIRECTION", codes)

    def test_linter_warns_on_generic_quality_keyword_soup(self):
        result = lint_prompt(
            "portrait, masterpiece, best quality, 8k, ultra detailed, soft studio light",
            "watermark",
        )
        self.assertTrue(result["ok"])
        codes = {item["code"] for item in result["issues"]}
        self.assertIn("QUALITY_KEYWORD_SOUP", codes)

    def test_linter_warns_on_repeated_clause(self):
        result = lint_prompt(
            "black anodized speaker, soft neutral background, black anodized speaker, three-quarter angle, diffused light",
            "watermark",
        )
        self.assertTrue(result["ok"])
        codes = {item["code"] for item in result["issues"]}
        self.assertIn("REPEATED_CLAUSE", codes)

    def test_golden_corpus_is_valid_versioned_and_fingerprinted(self):
        corpus = load_prompt_corpus(ROOT / "config" / "quality-golden-prompts-v1.json")
        self.assertEqual(corpus["prompt_set_version"], "quality-golden-v1")
        self.assertEqual(
            set(corpus["prompts"]),
            {"product", "portrait", "landscape", "interior", "game_art"},
        )
        self.assertEqual(len(corpus["sha256"]), 64)
        for prompt_id, spec in corpus["prompts"].items():
            with self.subTest(prompt_id=prompt_id):
                self.assertTrue(spec["lint"]["ok"])
                self.assertIsInstance(spec.get("review_focus"), list)
                self.assertGreaterEqual(len(spec["review_focus"]), 4)

    def test_corpus_fails_closed_on_lint_error(self):
        with tempfile.TemporaryDirectory() as value:
            path = Path(value) / "bad.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "prompt_set_version": "bad-v1",
                        "prompts": {
                            "bad": {
                                "prompt": "fixed front-on room, isometric view, soft window light",
                                "negative": "watermark",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "lint errors"):
                load_prompt_corpus(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
