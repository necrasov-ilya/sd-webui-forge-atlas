import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modules_forge import model_library


class ModelLibraryTests(unittest.TestCase):
    def test_empty_atlas_placeholder_is_repaired(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "external" / "Stable-diffusion"
            link = root / "atlas" / "Stable-diffusion" / model_library.LINK_NAME
            source.mkdir(parents=True)
            link.mkdir(parents=True)

            self.assertEqual(model_library._prepare_library_link(link, source), "create")
            self.assertFalse(link.exists())

    def test_nonempty_regular_atlas_folder_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "external" / "Stable-diffusion"
            link = root / "atlas" / "Stable-diffusion" / model_library.LINK_NAME
            source.mkdir(parents=True)
            link.mkdir(parents=True)
            marker = link / "keep.txt"
            marker.write_text("user data", encoding="utf-8")

            self.assertEqual(model_library._prepare_library_link(link, source), "conflict")
            self.assertTrue(marker.exists())

    def test_connected_empty_library_is_not_reported_as_already_installed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = root / "external"
            atlas_models = root / "atlas-models"
            (library / "Stable-diffusion").mkdir(parents=True)
            (atlas_models / "Stable-diffusion" / model_library.LINK_NAME).mkdir(parents=True)

            def make_placeholder(_source: Path, destination: Path):
                destination.mkdir()

            with (
                mock.patch.object(model_library.paths, "models_path", str(atlas_models)),
                mock.patch.object(model_library, "_create_directory_link", side_effect=make_placeholder),
                mock.patch.object(model_library, "_refresh_model_choices", return_value=([], [])),
            ):
                message, checkpoints, modules = model_library.connect_library(str(library))

            self.assertIn("файлов моделей в них не найдено", message)
            self.assertNotIn("уже подключена", message)
            self.assertEqual(checkpoints, [])
            self.assertEqual(modules, [])


if __name__ == "__main__":
    unittest.main()
