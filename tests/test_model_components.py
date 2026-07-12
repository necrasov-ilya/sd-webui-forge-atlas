import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import torch
from safetensors.torch import save_file

from modules_forge.model_components.download import validate_component
from modules_forge.model_components.inspector import inspect_checkpoint
from modules_forge.model_components.registry import COMPONENTS, FAMILY_BUNDLES, ComponentSpec


class ModelComponentTests(unittest.TestCase):
    def test_registry_files_are_pinned_and_never_point_to_checkpoint_folder(self):
        self.assertTrue(COMPONENTS)
        for component in COMPONENTS.values():
            self.assertGreater(component.size, 0)
            self.assertEqual(len(component.sha256), 64)
            self.assertIn(component.kind, {"vae", "text_encoder"})

    def test_inspection_distinguishes_embedded_installed_and_missing(self):
        bundle = FAMILY_BUNDLES["black-forest-labs/FLUX.1-dev"]
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "model.safetensors"
            save_file(
                {
                    "model.fake.weight": torch.zeros(1),
                    "text_encoders.clip_l.fake.weight": torch.zeros(1),
                },
                checkpoint,
            )
            with mock.patch("modules_forge.model_components.inspector._guess_bundle", return_value=bundle):
                result = inspect_checkpoint(str(checkpoint), ["t5xxl_fp8_e4m3fn_scaled.safetensors"])
        self.assertEqual(result.preset, "flux")
        self.assertEqual(result.embedded, ("clip_l",))
        self.assertEqual(result.installed, ("t5xxl",))
        self.assertEqual(result.missing, ("flux_ae",))

    def test_unknown_legacy_checkpoint_stays_manual(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "legacy.ckpt"
            checkpoint.write_bytes(b"not loaded")
            result = inspect_checkpoint(str(checkpoint))
        self.assertFalse(result.recognized)
        self.assertIn("вручную", result.message)

    def test_component_validation_checks_safetensors_and_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "component.safetensors"
            save_file({"weight": torch.zeros(1)}, path)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            spec = ComponentSpec("test", "Test", "vae", "example/repo", "revision", "component.safetensors", path.name, path.stat().st_size, digest, "MIT", ("vae.",))
            self.assertTrue(validate_component(path, spec)[0])
            wrong = ComponentSpec(**{**spec.__dict__, "sha256": "0" * 64})
            self.assertFalse(validate_component(path, wrong)[0])


if __name__ == "__main__":
    unittest.main()
