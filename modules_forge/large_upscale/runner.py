from __future__ import annotations

import math
import os
import shutil
import tempfile
from io import BytesIO
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np
import piexif
from PIL import Image, ImageCms, ImageOps

from modules_forge.large_upscale.contracts import LargeUpscaleJobSpec, LargeUpscaleManifest, LargeUpscaleResult, TileRegion
from modules_forge.large_upscale.manifest import save_manifest
from modules_forge.large_upscale.preflight import build_preflight
from modules_forge.large_upscale.raster import create_proxy_from_raster, create_raster, open_raster, write_pillow_from_mmap, write_png_streaming
from modules_forge.large_upscale.source import open_local_image, source_is_unchanged


ProgressCallback = Callable[[float, str], None]
CancelCallback = Callable[[], bool]
TileProcessor = Callable[[Image.Image, LargeUpscaleJobSpec, TileRegion], Image.Image]


class LargeUpscaleCancelled(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_progress(_value: float, _message: str) -> None:
    return None


def _default_cancel() -> bool:
    return False


def _working_directory(spec: LargeUpscaleJobSpec) -> Path:
    root = Path(spec.temp_root) if spec.temp_root else Path(tempfile.gettempdir()) / "forge-atlas" / "large-upscale"
    return root.expanduser().resolve() / spec.job_id


class SourceRegionReader:
    def __init__(self, spec: LargeUpscaleJobSpec):
        self.spec = spec
        self._vips = None
        self._opened = None
        self._image = None
        try:
            import pyvips

            self._vips = pyvips.Image.new_from_file(spec.source.path, access="random").autorot()
        except Exception as vips_error:
            if spec.source.pixels > 250_000_000:
                raise RuntimeError(f"libvips не смог открыть большой исходник в bounded-режиме: {vips_error}") from vips_error
            self._opened = open_local_image(spec.source.path)
            self._image = ImageOps.exif_transpose(self._opened)

    def close(self) -> None:
        self._vips = None
        if self._image is not None and self._image is not self._opened:
            self._image.close()
        if self._opened is not None:
            self._opened.close()

    def __enter__(self) -> "SourceRegionReader":
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def read(self, region: TileRegion, mode: str = "RGB") -> Image.Image:
        sx = self.spec.source.width / self.spec.target_width
        sy = self.spec.source.height / self.spec.target_height
        left = max(0, math.floor(region.x * sx))
        top = max(0, math.floor(region.y * sy))
        right = min(self.spec.source.width, math.ceil(region.right * sx))
        bottom = min(self.spec.source.height, math.ceil(region.bottom * sy))
        if self._vips is not None:
            cropped_vips = self._vips.crop(left, top, right - left, bottom - top)
            if cropped_vips.bands > 4 or cropped_vips.interpretation not in {"srgb", "rgb"}:
                cropped_vips = cropped_vips.colourspace("srgb")
            cropped_vips = cropped_vips.cast("uchar")
            memory = cropped_vips.write_to_memory()
            pixels = np.frombuffer(memory, dtype=np.uint8).reshape(cropped_vips.height, cropped_vips.width, cropped_vips.bands)
            if cropped_vips.bands == 1:
                pixels = np.repeat(pixels, 3, axis=2)
            elif cropped_vips.bands == 2:
                pixels = np.concatenate((np.repeat(pixels[:, :, :1], 3, axis=2), pixels[:, :, 1:2]), axis=2)
            pil_mode = "RGBA" if pixels.shape[2] >= 4 else "RGB"
            cropped = Image.fromarray(np.ascontiguousarray(pixels[:, :, :4 if pil_mode == "RGBA" else 3]), mode=pil_mode)
        else:
            cropped = self._image.crop((left, top, right, bottom))
        alpha = cropped.convert("RGBA").getchannel("A") if mode == "RGBA" else None
        cropped = cropped.convert("RGB")
        scale = max(region.width / max(1, cropped.width), region.height / max(1, cropped.height))
        if scale > 1 and self.spec.upscaler_name not in {"None", "Lanczos"}:
            from modules import shared

            selected = next((item for item in shared.sd_upscalers if item.name == self.spec.upscaler_name), None)
            if selected is not None:
                cropped = selected.scaler.upscale(cropped, scale, selected.data_path)
        if cropped.size != (region.width, region.height):
            cropped = cropped.resize((region.width, region.height), Image.Resampling.LANCZOS)
        if alpha is not None:
            alpha = alpha.resize((region.width, region.height), Image.Resampling.LANCZOS)
            cropped.putalpha(alpha)
        return cropped


def _tile_path(work: Path, index: int) -> Path:
    return work / "tiles" / f"tile-{index:08d}.png"


def _manifest_path(work: Path) -> Path:
    return work / "manifest.json"


def _load_or_create_manifest(spec: LargeUpscaleJobSpec, work: Path) -> LargeUpscaleManifest:
    path = _manifest_path(work)
    if spec.resume_enabled and path.is_file():
        existing = LargeUpscaleManifest.load(path)
        if existing.spec != spec:
            raise ValueError("Настройки незавершённой задачи отличаются. Начни новую задачу или верни прежние параметры.")
        existing.status = "created"
        existing.error = None
        return existing

    report = build_preflight(spec)
    if not report.can_start:
        raise ValueError(" ".join(report.errors))
    now = _now()
    return LargeUpscaleManifest(
        spec=spec,
        tiles=list(report.tiles),
        created_at=now,
        updated_at=now,
        working_directory=str(work),
        working_raster=str(work / "assembled.rgb"),
    )


def _save_state(manifest: LargeUpscaleManifest, work: Path) -> None:
    manifest.updated_at = _now()
    save_manifest(manifest, _manifest_path(work))


def _check_cancel(cancel: CancelCallback) -> None:
    if cancel():
        raise LargeUpscaleCancelled("Улучшение отменено. Временные тайлы сохранены для продолжения.")


def _blend_ramp(length: int, mode: str, reverse: bool = False) -> np.ndarray:
    if length <= 0:
        return np.ones((0,), dtype=np.float32)
    values = np.linspace(0, 1, length, dtype=np.float32)
    if mode == "cosine":
        values = 0.5 - 0.5 * np.cos(values * np.pi)
    return values[::-1] if reverse else values


def _tile_weight(tile: TileRegion, image_width: int, image_height: int, mode: str) -> np.ndarray:
    wx = np.ones(tile.width, dtype=np.float32)
    wy = np.ones(tile.height, dtype=np.float32)
    left = tile.core_x - tile.x
    top = tile.core_y - tile.y
    right_start = tile.core_x + tile.core_width - tile.x
    bottom_start = tile.core_y + tile.core_height - tile.y
    if tile.x > 0 and left > 0:
        wx[:left] = _blend_ramp(left, mode)
    if tile.right < image_width and right_start < tile.width:
        wx[right_start:] = _blend_ramp(tile.width - right_start, mode, reverse=True)
    if tile.y > 0 and top > 0:
        wy[:top] = _blend_ramp(top, mode)
    if tile.bottom < image_height and bottom_start < tile.height:
        wy[bottom_start:] = _blend_ramp(tile.height - bottom_start, mode, reverse=True)
    return wy[:, None] * wx[None, :]


def _intersects(tile: TileRegion, x: int, y: int, width: int, height: int) -> bool:
    return tile.x < x + width and tile.right > x and tile.y < y + height and tile.bottom > y


def _assemble(manifest: LargeUpscaleManifest, work: Path, progress: ProgressCallback, cancel: CancelCallback) -> np.memmap:
    spec = manifest.spec
    raster_path = Path(manifest.working_raster)
    channels = 4 if spec.source.has_alpha and spec.keep_alpha and spec.output_format.lower() in {"png", "webp"} else 3
    raster = create_raster(raster_path, spec.target_width, spec.target_height, channels)
    block_size = spec.assembly_block_size
    block_columns = math.ceil(spec.target_width / block_size)
    block_rows = math.ceil(spec.target_height / block_size)
    total_blocks = block_columns * block_rows
    block_index = 0

    for y in range(0, spec.target_height, block_size):
        block_height = min(block_size, spec.target_height - y)
        for x in range(0, spec.target_width, block_size):
            _check_cancel(cancel)
            block_width = min(block_size, spec.target_width - x)
            accumulator = np.zeros((block_height, block_width, channels), dtype=np.float32)
            weight_sum = np.zeros((block_height, block_width), dtype=np.float32)
            for tile in manifest.tiles:
                if not _intersects(tile, x, y, block_width, block_height):
                    continue
                left = max(x, tile.x)
                top = max(y, tile.y)
                right = min(x + block_width, tile.right)
                bottom = min(y + block_height, tile.bottom)
                tile_box = (left - tile.x, top - tile.y, right - tile.x, bottom - tile.y)
                with Image.open(_tile_path(work, tile.index)) as opened:
                    pixels = np.asarray(opened.convert("RGBA" if channels == 4 else "RGB").crop(tile_box), dtype=np.float32)
                tile_weights = _tile_weight(tile, spec.target_width, spec.target_height, spec.seam_blending)
                weight = tile_weights[tile_box[1] : tile_box[3], tile_box[0] : tile_box[2]]
                by0, by1 = top - y, bottom - y
                bx0, bx1 = left - x, right - x
                accumulator[by0:by1, bx0:bx1] += pixels * weight[..., None]
                weight_sum[by0:by1, bx0:bx1] += weight
            if np.any(weight_sum <= 0):
                raise RuntimeError("Не удалось собрать результат: в сетке обнаружен незаполненный участок.")
            raster[y : y + block_height, x : x + block_width] = np.clip(accumulator / weight_sum[..., None], 0, 255).astype(np.uint8)
            raster.flush()
            block_index += 1
            progress(0.78 + 0.14 * block_index / total_blocks, f"Сборка результата: блок {block_index} из {total_blocks}")
    return raster


def _source_icc(spec: LargeUpscaleJobSpec) -> bytes | None:
    if not spec.keep_icc or not spec.source.has_icc:
        return None
    with open_local_image(spec.source.path) as image:
        return image.info.get("icc_profile")


def _infotext(spec: LargeUpscaleJobSpec) -> str:
    negative = f"\nNegative prompt: {spec.negative_prompt}" if spec.negative_prompt else ""
    return (
        f"{spec.prompt}{negative}\n"
        f"Atlas Ultra-Large Upscale, Steps: {spec.steps}, Sampler: {spec.sampler_name or 'Automatic'}, "
        f"Schedule type: {spec.scheduler or 'Automatic'}, CFG scale: {spec.cfg_scale}, "
        f"Distilled CFG: {spec.distilled_cfg_scale}, Seed: {spec.seed}, Denoising strength: {spec.denoising_strength}, "
        f"Size: {spec.target_width}x{spec.target_height}, Tile: {spec.tile_width}x{spec.tile_height}, Overlap: {spec.overlap}, "
        f"Model: {spec.checkpoint or 'None'}, AutoPrompt profile: {spec.analysis_profile or 'manual'}"
    )


def _output_exif(spec: LargeUpscaleJobSpec, infotext: str) -> bytes | None:
    if not spec.keep_metadata:
        return None
    try:
        with open_local_image(spec.source.path) as image:
            source_exif = image.info.get("exif")
        exif = piexif.load(source_exif) if source_exif else {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
    except Exception:
        exif = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
    exif["0th"].pop(piexif.ImageIFD.Orientation, None)
    exif["Exif"][piexif.ExifIFD.UserComment] = b"UNICODE\x00" + infotext.encode("utf-16-be")
    return piexif.dump(exif)


def _export(manifest: LargeUpscaleManifest, raster: np.memmap, work: Path) -> Path:
    spec = manifest.spec
    output = Path(spec.output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output_format = spec.output_format.lower()
    icc_profile = _source_icc(spec)
    infotext = _infotext(spec)
    exif_bytes = _output_exif(spec, infotext)
    if output_format == "png":
        write_png_streaming(raster, output, infotext=infotext if spec.keep_metadata else "", icc_profile=icc_profile, exif_bytes=exif_bytes)
    elif output_format in {"jpg", "jpeg", "webp"}:
        write_pillow_from_mmap(
            manifest.working_raster,
            spec.target_width,
            spec.target_height,
            output,
            "JPEG" if output_format in {"jpg", "jpeg"} else "WEBP",
            channels=raster.shape[2],
            quality=spec.jpeg_quality,
            lossless=spec.webp_lossless,
            icc_profile=icc_profile,
            exif_bytes=exif_bytes,
        )
    else:
        raise ValueError(f"Disk-backed экспорт {output_format.upper()} пока не поддерживается. Выбери PNG, JPEG или WebP.")
    return output


def run_large_upscale(
    spec: LargeUpscaleJobSpec,
    tile_processor: TileProcessor,
    *,
    progress: ProgressCallback = _default_progress,
    cancelled: CancelCallback = _default_cancel,
) -> LargeUpscaleResult:
    """Run one immutable large-image job. The caller must hold Forge's GPU queue lock."""
    report = build_preflight(spec)
    if not report.can_start:
        raise ValueError(" ".join(report.errors))
    work = _working_directory(spec)
    (work / "tiles").mkdir(parents=True, exist_ok=True)
    manifest = _load_or_create_manifest(spec, work)
    manifest.status = "running"
    _save_state(manifest, work)

    try:
        source_icc = _source_icc(spec)
        to_srgb = None
        from_srgb = None
        if source_icc:
            source_profile = ImageCms.ImageCmsProfile(BytesIO(source_icc))
            srgb_profile = ImageCms.createProfile("sRGB")
            to_srgb = ImageCms.buildTransformFromOpenProfiles(source_profile, srgb_profile, "RGB", "RGB")
            from_srgb = ImageCms.buildTransformFromOpenProfiles(srgb_profile, source_profile, "RGB", "RGB")
        with SourceRegionReader(spec) as source:
            completed = set(manifest.completed_tiles)
            total = len(manifest.tiles)
            for position, tile in enumerate(manifest.tiles, start=1):
                _check_cancel(cancelled)
                tile_path = _tile_path(work, tile.index)
                if tile.index in completed and tile_path.is_file():
                    progress(0.72 * position / total, f"Тайл {position} из {total} уже готов")
                    continue
                if not source_is_unchanged(spec.source):
                    raise RuntimeError("Исходник изменился во время обработки. Задача остановлена до сборки результата.")
                preserve_alpha = spec.source.has_alpha and spec.keep_alpha and spec.output_format.lower() in {"png", "webp"}
                source_tile = source.read(tile, mode="RGBA" if preserve_alpha else "RGB")
                alpha = source_tile.getchannel("A") if preserve_alpha else None
                input_tile = source_tile.convert("RGB")
                if to_srgb is not None:
                    converted_input = ImageCms.applyTransform(input_tile, to_srgb)
                    input_tile.close()
                    input_tile = converted_input
                output_tile = None
                temporary = tile_path.with_suffix(".tmp")
                try:
                    output_tile = tile_processor(input_tile, spec, tile)
                    _check_cancel(cancelled)
                    if not source_is_unchanged(spec.source):
                        raise RuntimeError("Исходник изменился во время обработки тайла. Результат тайла не сохранён.")
                    if output_tile.size != input_tile.size:
                        resized = output_tile.resize(input_tile.size, Image.Resampling.LANCZOS)
                        output_tile.close()
                        output_tile = resized
                    converted = output_tile.convert("RGB")
                    if converted is not output_tile:
                        output_tile.close()
                    output_tile = converted
                    if from_srgb is not None:
                        converted_output = ImageCms.applyTransform(output_tile, from_srgb)
                        output_tile.close()
                        output_tile = converted_output
                    if alpha is not None:
                        output_tile.putalpha(alpha)
                    output_tile.save(temporary, format="PNG", compress_level=1)
                    os.replace(temporary, tile_path)
                finally:
                    input_tile.close()
                    source_tile.close()
                    if alpha is not None:
                        alpha.close()
                    if output_tile is not None:
                        output_tile.close()
                    try:
                        temporary.unlink()
                    except OSError:
                        pass
                manifest.completed_tiles.append(tile.index)
                _save_state(manifest, work)
                progress(0.72 * position / total, f"Обработан тайл {position} из {total}")

        progress(0.74, "Собираю результат без загрузки полного изображения в память")
        raster = _assemble(manifest, work, progress, cancelled)
        _check_cancel(cancelled)
        progress(0.94, "Записываю финальный файл")
        output = _export(manifest, raster, work)
        proxy = work / "result-proxy.webp"
        create_proxy_from_raster(raster, proxy, spec.proxy_max_side, spec.proxy_max_payload_bytes)
        del raster

        sidecar_manifest = output.with_suffix(output.suffix + ".atlas.json")
        final_proxy = output.with_suffix(output.suffix + ".proxy.webp")
        os.replace(proxy, final_proxy)
        manifest.status = "completed"
        manifest.result_path = str(output)
        manifest.proxy_path = str(final_proxy)
        manifest.error = None
        _save_state(manifest, work)
        save_manifest(manifest, sidecar_manifest)
        progress(1.0, "Готово")

        result = LargeUpscaleResult(
            path=str(output),
            proxy_path=str(final_proxy),
            width=spec.target_width,
            height=spec.target_height,
            format=spec.output_format.upper(),
            file_size=output.stat().st_size,
            infotext=_infotext(spec),
            manifest_path=str(sidecar_manifest),
        )
        if spec.cleanup_after_success:
            shutil.rmtree(work, ignore_errors=True)
        return result
    except LargeUpscaleCancelled as error:
        manifest.status = "cancelled"
        manifest.error = str(error)
        _save_state(manifest, work)
        raise
    except Exception as error:
        manifest.status = "failed"
        manifest.error = f"{type(error).__name__}: {error}"
        _save_state(manifest, work)
        if not spec.keep_temp_on_error:
            shutil.rmtree(work, ignore_errors=True)
        raise


def forge_tile_processor(image: Image.Image, spec: LargeUpscaleJobSpec, tile: TileRegion) -> Image.Image:
    """Adapter to the unchanged Forge img2img processing contract."""
    from modules import devices, processing, shared

    if shared.opts.sd_model_checkpoint != spec.checkpoint or tuple(shared.opts.forge_additional_modules) != spec.additional_modules:
        raise RuntimeError("Checkpoint, VAE или text encoder изменились после preflight. Верни выбор или начни новую задачу.")

    original_size = image.size
    padded_width = math.ceil(image.width / 8) * 8
    padded_height = math.ceil(image.height / 8) * 8
    if (padded_width, padded_height) != image.size:
        pixels = np.asarray(image.convert("RGB"))
        pixels = np.pad(pixels, ((0, padded_height - image.height), (0, padded_width - image.width), (0, 0)), mode="edge")
        image = Image.fromarray(pixels, mode="RGB")

    processor = processing.StableDiffusionProcessingImg2Img(
        outpath_samples=shared.opts.outdir_img2img_samples,
        outpath_grids=shared.opts.outdir_img2img_grids,
        prompt=spec.prompt,
        negative_prompt=spec.negative_prompt,
        seed=(spec.seed + tile.index) % (2**32),
        sampler_name=spec.sampler_name,
        scheduler=spec.scheduler,
        batch_size=1,
        n_iter=1,
        steps=spec.steps,
        cfg_scale=spec.cfg_scale,
        distilled_cfg_scale=spec.distilled_cfg_scale,
        width=padded_width,
        height=padded_height,
        init_images=[image],
        resize_mode=3,
        denoising_strength=spec.denoising_strength,
        do_not_save_samples=True,
        do_not_save_grid=True,
    )
    try:
        processed = processing.process_images(processor)
        if not processed.images:
            raise RuntimeError("Forge не вернул изображение для тайла.")
        result = processed.images[0].convert("RGB")
        if result.size != original_size:
            result = result.crop((0, 0, original_size[0], original_size[1]))
        return result
    finally:
        processor.close()
        devices.torch_gc()
