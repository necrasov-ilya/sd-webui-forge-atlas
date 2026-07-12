from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from PIL import Image, ImageCms
import piexif

from modules_forge.large_upscale.contracts import LargeUpscaleJobSpec
from modules_forge.large_upscale.contracts import LargeUpscaleManifest
from modules_forge.large_upscale.runner import LargeUpscaleCancelled, run_large_upscale
from modules_forge.large_upscale.source import inspect_source


class LargeUpscaleRunnerTests(unittest.TestCase):
    def _spec(self, directory: str, cleanup: bool = False) -> LargeUpscaleJobSpec:
        root = Path(directory)
        source_path = root / "source.png"
        Image.new("RGB", (41, 35), (70, 120, 180)).save(source_path)
        source = inspect_source(source_path, proxy_max_side=256, proxy_dir=root / "proxies")
        return LargeUpscaleJobSpec(
            job_id="bounded-e2e",
            source=source,
            target_width=77,
            target_height=65,
            prompt="soft painterly texture, balanced light",
            checkpoint="unit-test.safetensors",
            output_path=str(root / "result.png"),
            output_format="png",
            temp_root=str(root / "work"),
            tile_width=40,
            tile_height=40,
            overlap=8,
            assembly_block_size=32,
            proxy_max_side=256,
            cleanup_after_success=cleanup,
        )

    def test_bounded_end_to_end_creates_file_and_proxy(self):
        with tempfile.TemporaryDirectory() as directory:
            spec = self._spec(directory, cleanup=True)
            result = run_large_upscale(spec, lambda image, _spec, _tile: image.copy())
            self.assertTrue(Path(result.path).is_file())
            self.assertTrue(Path(result.proxy_path).is_file())
            with Image.open(result.path) as output:
                self.assertEqual(output.size, (77, 65))
            with Image.open(result.proxy_path) as proxy:
                self.assertLessEqual(max(proxy.size), 256)

    def test_cancelled_job_resumes_completed_tiles(self):
        with tempfile.TemporaryDirectory() as directory:
            spec = self._spec(directory)
            calls = 0
            stop = False

            def processor(image, _spec, _tile):
                nonlocal calls
                calls += 1
                return image.copy()

            def progress(_value, message):
                nonlocal stop
                if "Обработан тайл 1" in message:
                    stop = True

            with self.assertRaises(LargeUpscaleCancelled):
                run_large_upscale(spec, processor, progress=progress, cancelled=lambda: stop)
            first_run_calls = calls
            result = run_large_upscale(spec, processor)
            self.assertTrue(Path(result.path).is_file())
            self.assertLess(calls - first_run_calls, calls)

    def test_png_preserves_alpha_without_full_browser_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "alpha.png"
            Image.new("RGBA", (19, 17), (80, 100, 120, 96)).save(source_path)
            source = inspect_source(source_path, proxy_max_side=256, proxy_dir=root / "proxies")
            spec = LargeUpscaleJobSpec(
                job_id="alpha-e2e",
                source=source,
                target_width=37,
                target_height=31,
                prompt="soft texture",
                checkpoint="unit-test.safetensors",
                output_path=str(root / "alpha-result.png"),
                output_format="png",
                temp_root=str(root / "work"),
                tile_width=32,
                tile_height=32,
                overlap=4,
                assembly_block_size=16,
                proxy_max_side=64,
                keep_alpha=True,
            )
            result = run_large_upscale(spec, lambda image, _spec, _tile: image.copy())
            with Image.open(result.path) as output:
                self.assertEqual(output.mode, "RGBA")
                self.assertLess(output.getchannel("A").getextrema()[0], 255)
            with Image.open(result.proxy_path) as proxy:
                self.assertLessEqual(max(proxy.size), 64)

    def test_webp_preserves_alpha_with_bounded_dimensions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "alpha.png"
            Image.new("RGBA", (17, 13), (30, 60, 90, 110)).save(source_path)
            source = inspect_source(source_path, proxy_max_side=256, proxy_dir=root / "proxies")
            spec = LargeUpscaleJobSpec(
                job_id="alpha-webp",
                source=source,
                target_width=29,
                target_height=23,
                prompt="soft texture",
                checkpoint="unit-test.safetensors",
                output_path=str(root / "result.webp"),
                output_format="webp",
                temp_root=str(root / "work"),
                tile_width=32,
                tile_height=32,
                overlap=4,
                assembly_block_size=16,
                keep_alpha=True,
            )
            result = run_large_upscale(spec, lambda image, _spec, _tile: image.copy())
            with Image.open(result.path) as output:
                self.assertEqual(output.mode, "RGBA")

    def test_processing_failure_is_recorded_for_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            spec = self._spec(directory)

            def fail(_image, _spec, _tile):
                raise RuntimeError("synthetic encoder failure")

            with self.assertRaisesRegex(RuntimeError, "synthetic encoder failure"):
                run_large_upscale(spec, fail)
            manifest = LargeUpscaleManifest.load(Path(directory) / "work" / spec.job_id / "manifest.json")
            self.assertEqual(manifest.status, "failed")
            self.assertIn("synthetic encoder failure", manifest.error)

    def test_png_preserves_rgb_icc_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "icc.png"
            icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
            Image.new("RGB", (13, 11), (40, 80, 120)).save(source_path, icc_profile=icc)
            source = inspect_source(source_path, proxy_max_side=256, proxy_dir=root / "proxies")
            spec = LargeUpscaleJobSpec(
                job_id="icc-e2e",
                source=source,
                target_width=23,
                target_height=19,
                prompt="natural light",
                checkpoint="unit-test.safetensors",
                output_path=str(root / "result.png"),
                output_format="png",
                temp_root=str(root / "work"),
                tile_width=32,
                tile_height=32,
                overlap=4,
                assembly_block_size=16,
                keep_icc=True,
            )
            result = run_large_upscale(spec, lambda image, _spec, _tile: image.copy())
            with Image.open(result.path) as output:
                self.assertTrue(output.info.get("icc_profile"))

    def test_jpeg_embeds_infotext_without_gallery_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            spec = replace(self._spec(directory), job_id="jpeg-metadata", output_path=str(Path(directory) / "result.jpg"), output_format="jpg")
            result = run_large_upscale(spec, lambda image, _spec, _tile: image.copy())
            exif = piexif.load(result.path)
            comment = exif["Exif"][piexif.ExifIFD.UserComment]
            self.assertIn("Atlas Ultra-Large Upscale", comment.decode("utf-16-be", errors="ignore"))


if __name__ == "__main__":
    unittest.main()
