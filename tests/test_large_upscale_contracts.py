from __future__ import annotations

import json
import tempfile
import tracemalloc
import unittest
from dataclasses import replace
from pathlib import Path

from PIL import Image

from modules_forge.large_upscale.contracts import LargeUpscaleJobSpec, LargeUpscaleManifest, SourceAsset
from modules_forge.large_upscale.manifest import save_manifest
from modules_forge.large_upscale.preflight import build_preflight, calculate_tiles
from modules_forge.large_upscale.source import inspect_source, source_fingerprint


class LargeUpscaleContractsTests(unittest.TestCase):
    def test_50k_grid_is_metadata_only_and_covers_edges(self):
        for width, height in ((10_003, 7_007), (20_003, 12_007), (50_003, 20_007)):
            tiles = calculate_tiles(width, height, 1024, 1024, 128)
            self.assertGreater(len(tiles), 1)
            self.assertEqual(max(tile.right for tile in tiles), width)
            self.assertEqual(max(tile.bottom for tile in tiles), height)
            self.assertEqual(tiles[0].x, 0)
            self.assertEqual(tiles[0].y, 0)

    def test_overlap_must_leave_a_core(self):
        with self.assertRaises(ValueError):
            calculate_tiles(1024, 1024, 512, 512, 256)

    def test_50k_preflight_does_not_allocate_full_raster(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "metadata-only.png"
            Image.new("RGB", (8, 8)).save(source_path)
            source = SourceAsset(
                path=str(source_path),
                fingerprint=source_fingerprint(source_path),
                width=50_000,
                height=50_000,
                format="PNG",
                file_size=source_path.stat().st_size,
                mode="RGB",
            )
            spec = LargeUpscaleJobSpec(
                job_id="50k-preflight",
                source=source,
                target_width=50_000,
                target_height=50_000,
                prompt="cohesive light",
                checkpoint="test.safetensors",
                output_path=str(Path(directory) / "result.png"),
                temp_root=directory,
            )
            tracemalloc.start()
            report = build_preflight(spec)
            _current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            self.assertGreater(len(report.tiles), 1000)
            self.assertLess(peak, 64 * 1024 * 1024)

    def test_source_and_proxy_are_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "исходник.png"
            Image.new("RGBA", (80, 40), (12, 34, 56, 128)).save(source)
            asset = inspect_source(source, proxy_max_side=256, proxy_dir=Path(directory) / "proxy")
            self.assertEqual(asset.path, str(source.resolve()))
            self.assertNotEqual(asset.path, asset.proxy_path)
            self.assertTrue(Path(asset.proxy_path).is_file())
            self.assertTrue(asset.has_alpha)

    def test_exif_orientation_is_reflected_in_source_metadata_and_proxy(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "rotated.jpg"
            exif = Image.Exif()
            exif[274] = 6
            Image.new("RGB", (24, 12), (30, 60, 90)).save(source, exif=exif)
            asset = inspect_source(source, proxy_max_side=256, proxy_dir=Path(directory) / "proxy")
            self.assertEqual((asset.width, asset.height), (12, 24))
            with Image.open(asset.proxy_path) as proxy:
                self.assertEqual(proxy.size, (12, 24))

    def test_manifest_roundtrip_and_atomic_write(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "source.png"
            Image.new("RGB", (16, 16)).save(source_path)
            source = SourceAsset(
                path=str(source_path),
                fingerprint=source_fingerprint(source_path),
                width=16,
                height=16,
                format="PNG",
                file_size=source_path.stat().st_size,
                mode="RGB",
            )
            spec = LargeUpscaleJobSpec(
                job_id="unit-test",
                source=source,
                target_width=33,
                target_height=31,
                prompt="soft light",
                checkpoint="test.safetensors",
                output_path=str(Path(directory) / "result.png"),
                temp_root=directory,
                tile_width=32,
                tile_height=32,
                overlap=4,
            )
            report = build_preflight(spec)
            self.assertTrue(report.can_start, report.errors)
            manifest = LargeUpscaleManifest(spec=spec, tiles=list(report.tiles))
            path = Path(directory) / "manifest.json"
            save_manifest(manifest, path)
            loaded = LargeUpscaleManifest.load(path)
            self.assertEqual(loaded.spec.source.fingerprint, source.fingerprint)
            self.assertEqual(loaded.tiles[-1].right, 33)
            json.loads(path.read_text(encoding="utf-8"))

            webp_report = build_preflight(replace(spec, target_width=16_384, output_format="webp", output_path=str(Path(directory) / "large.webp")))
            self.assertTrue(any("16383" in error for error in webp_report.errors))


if __name__ == "__main__":
    unittest.main()
