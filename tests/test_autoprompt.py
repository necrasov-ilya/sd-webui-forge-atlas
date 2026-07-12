from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modules_forge.autoprompt.compiler import compile_tile_safe_prompt
from modules_forge.autoprompt.download import FLORENCE_FILES, FLORENCE_TOTAL_BYTES, validate_florence_directory


class AutopromptTests(unittest.TestCase):
    def test_compiler_keeps_global_style_and_drops_local_facts(self):
        raw = (
            'A cinematic digital illustration of Alice and 3 robots beside a sign saying "NORTH 42". '
            "The wide-angle city scene has neon lighting, cool colors, high contrast and crisp intricate detail."
        )
        prompt = compile_tile_safe_prompt(raw)
        self.assertIn("digital illustration", prompt)
        self.assertIn("wide composition", prompt)
        self.assertIn("neon lighting", prompt)
        self.assertIn("cool color palette", prompt)
        self.assertNotIn("Alice", prompt)
        self.assertNotIn("robot", prompt)
        self.assertNotRegex(prompt, r"\d")

    def test_compiler_is_deterministic_and_bounded(self):
        raw = "A watercolor landscape with soft diffused light, pastel colors, calm atmosphere and visible brushwork."
        first = compile_tile_safe_prompt(raw, 120)
        self.assertEqual(first, compile_tile_safe_prompt(raw, 120))
        self.assertLessEqual(len(first), 120)

    def test_compiler_covers_common_visual_media(self):
        samples = {
            "photograph": "A cinematic photograph with natural light, muted colors and fine natural texture.",
            "oil painting": "An oil painting with dramatic directional light, warm colors and visible brushwork.",
            "digital illustration": "A digital illustration with vibrant colors, dynamic composition and crisp detail.",
            "3D render": "A polished 3D render with studio lighting, high contrast and smooth rendering.",
            "anime artwork": "Anime artwork with pastel colors, soft diffused light and a calm atmosphere.",
            "architectural scene": "An architectural interior with a wide-angle view, cool ambient light and symmetry.",
        }
        for expected, caption in samples.items():
            with self.subTest(expected=expected):
                self.assertIn(expected, compile_tile_safe_prompt(caption))

    def test_download_allowlist_excludes_remote_code_and_bin(self):
        self.assertIn("model.safetensors", FLORENCE_FILES)
        self.assertNotIn("pytorch_model.bin", FLORENCE_FILES)
        self.assertFalse(any(name.endswith(".py") for name in FLORENCE_FILES))
        self.assertGreater(FLORENCE_TOTAL_BYTES, 440 * 1024 * 1024)
        self.assertLess(FLORENCE_TOTAL_BYTES, 450 * 1024 * 1024)

    def test_incomplete_directory_is_not_installed(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "config.json").write_text("{}", encoding="utf-8")
            valid, message = validate_florence_directory(directory)
            self.assertFalse(valid)
            self.assertIn("Не хватает", message)


if __name__ == "__main__":
    unittest.main()
