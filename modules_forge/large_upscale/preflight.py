from __future__ import annotations

import math
import shutil
from dataclasses import dataclass
from pathlib import Path

import psutil

from modules_forge.large_upscale.contracts import LargeUpscaleJobSpec, TileRegion
from modules_forge.large_upscale.source import format_file_size, random_access_backend_available, source_is_unchanged


FORMAT_DIMENSION_LIMITS = {"jpg": 65535, "jpeg": 65535, "webp": 16383}


@dataclass(frozen=True)
class PreflightReport:
    tiles: tuple[TileRegion, ...]
    estimated_output_bytes: int
    estimated_temporary_bytes: int
    required_free_bytes: int
    available_free_bytes: int
    estimated_ram_bytes: int
    available_ram_bytes: int
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def can_start(self) -> bool:
        return not self.errors

    def to_markdown(self, target_width: int, target_height: int, output_format: str) -> str:
        state = "Готово к запуску" if self.can_start else "Нужно исправить"
        lines = [
            f"### {state}",
            f"**{target_width} × {target_height}** · {target_width * target_height:,} пикселей · {len(self.tiles)} тайлов · {output_format.upper()}",
            f"Финальный файл: примерно {format_file_size(self.estimated_output_bytes)} · временные данные: {format_file_size(self.estimated_temporary_bytes)} · свободно: {format_file_size(self.available_free_bytes)}",
            f"RAM рабочего набора: около {format_file_size(self.estimated_ram_bytes)} из доступных {format_file_size(self.available_ram_bytes)} · VRAM ограничена одним тайлом и зависит от выбранной модели",
        ]
        lines.extend(f"- ⛔ {message}" for message in self.errors)
        lines.extend(f"- ⚠️ {message}" for message in self.warnings)
        return "\n\n".join(lines)


def calculate_tiles(width: int, height: int, tile_width: int, tile_height: int, overlap: int) -> tuple[TileRegion, ...]:
    if width <= 0 or height <= 0:
        raise ValueError("Размер результата должен быть положительным.")
    if tile_width <= 0 or tile_height <= 0:
        raise ValueError("Размер тайла должен быть положительным.")
    if overlap < 0 or overlap * 2 >= min(tile_width, tile_height):
        raise ValueError("Overlap должен быть меньше половины меньшей стороны тайла.")

    core_width = tile_width - overlap * 2
    core_height = tile_height - overlap * 2
    columns = max(1, math.ceil(width / core_width))
    rows = max(1, math.ceil(height / core_height))
    result: list[TileRegion] = []
    index = 0
    for row in range(rows):
        core_y = row * core_height
        actual_core_height = min(core_height, height - core_y)
        for column in range(columns):
            core_x = column * core_width
            actual_core_width = min(core_width, width - core_x)
            x = max(0, core_x - overlap)
            y = max(0, core_y - overlap)
            right = min(width, core_x + actual_core_width + overlap)
            bottom = min(height, core_y + actual_core_height + overlap)
            result.append(TileRegion(index, x, y, right - x, bottom - y, core_x, core_y, actual_core_width, actual_core_height))
            index += 1
    return tuple(result)


def _free_space(path: Path) -> int:
    existing = path
    while not existing.exists() and existing.parent != existing:
        existing = existing.parent
    return shutil.disk_usage(existing).free


def build_preflight(spec: LargeUpscaleJobSpec) -> PreflightReport:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        tiles = calculate_tiles(spec.target_width, spec.target_height, spec.tile_width, spec.tile_height, spec.overlap)
    except ValueError as error:
        tiles = ()
        errors.append(str(error))

    if not source_is_unchanged(spec.source):
        errors.append("Исходник недоступен или изменился после выбора.")
    if not spec.checkpoint:
        errors.append("Не выбран checkpoint.")
    if spec.model_preset == "wan":
        errors.append("Видео-модели Wan нельзя использовать в workflow улучшения изображения. Выбери image checkpoint.")
    if spec.batch_size != 1:
        warnings.append("Для предсказуемого расхода памяти большие изображения обрабатываются по одному тайлу.")
    if spec.keep_icc and spec.source.has_icc and spec.source.mode not in {"RGB", "RGBA"}:
        errors.append(f"Безопасное сохранение ICC для режима {spec.source.mode} не проверено. Отключи сохранение ICC или заранее переведи исходник в RGB.")

    output = Path(spec.output_path).expanduser().resolve() if spec.output_path else Path.cwd() / "output.png"
    if output == Path(spec.source.path).resolve():
        errors.append("Путь результата совпадает с исходником.")
    limit = FORMAT_DIMENSION_LIMITS.get(spec.output_format.lower())
    if limit and max(spec.target_width, spec.target_height) > limit:
        errors.append(f"{spec.output_format.upper()} поддерживает сторону не больше {limit} px. Выбери потоковый PNG.")
    if spec.output_format.lower() not in {"png", "jpg", "jpeg", "webp"}:
        errors.append("Выбранный формат пока не имеет проверенного disk-backed encoder. Выбери PNG, JPEG или WebP.")
    if spec.output_format.lower() == "png" and max(spec.target_width, spec.target_height) > 2_147_483_647:
        errors.append("Размер стороны превышает проверенный предел PNG encoder (2 147 483 647 px).")
    if spec.seam_blending not in {"cosine", "feather"}:
        errors.append("Неизвестный режим смешивания границ.")
    if spec.assembly_block_size <= 0:
        errors.append("Размер блока сборки должен быть положительным.")

    channels = 4 if spec.source.has_alpha and spec.keep_alpha and spec.output_format.lower() in {"png", "webp"} else 3
    raw_bytes = spec.target_width * spec.target_height * channels
    output_ratio = 0.58 if spec.output_format.lower() == "png" else 0.32
    estimated_output = max(1024 * 1024, int(raw_bytes * output_ratio))
    tile_bytes = sum(tile.width * tile.height * 3 for tile in tiles)
    working_bytes = raw_bytes
    estimated_temporary = working_bytes + tile_bytes + max(64 * 1024 * 1024, spec.assembly_block_size**2 * 20)
    headroom = max(1024**3, int((estimated_temporary + estimated_output) * 0.1))
    required = estimated_temporary + estimated_output + headroom
    temp_available = _free_space(Path(spec.temp_root or output.parent))
    output_available = _free_space(output.parent)
    available = min(temp_available, output_available)
    if temp_available < estimated_temporary + headroom:
        errors.append(f"Во временной папке недостаточно места: нужно около {format_file_size(estimated_temporary + headroom)}, доступно {format_file_size(temp_available)}.")
    if output_available < estimated_output + headroom:
        errors.append(f"В папке результата недостаточно места: нужно около {format_file_size(estimated_output + headroom)}, доступно {format_file_size(output_available)}.")

    estimated_ram = spec.assembly_block_size**2 * 20 + spec.tile_width * spec.tile_height * 24
    available_ram = psutil.virtual_memory().available
    if estimated_ram > int(available_ram * 0.75):
        errors.append(f"Выбранные тайлы и блок сборки требуют около {format_file_size(estimated_ram)} RAM. Уменьши их размер.")
    if max(spec.tile_width, spec.tile_height) > 2048:
        warnings.append("Тайл больше 2048 px может не поместиться в VRAM выбранной diffusion-модели.")
    if spec.output_format.lower() == "webp" and raw_bytes > max(512 * 1024**2, int(available_ram * 0.4)):
        errors.append("WebP encoder не гарантирует bounded RAM для такого размера. Выбери потоковый PNG.")
    if spec.source.pixels > 250_000_000:
        if not random_access_backend_available():
            errors.append("Для безопасного чтения такого большого исходника нужен bundled libvips. Восстанови зависимости Forge Atlas и повтори проверку.")
        else:
            warnings.append("Большой исходник будет читаться через disk-backed libvips; полный RGB-буфер в RAM не создаётся.")
    if spec.overlap < 32:
        warnings.append("Маленький overlap может сделать границы тайлов заметными.")
    if spec.prompt and any(char.isdigit() for char in spec.prompt):
        warnings.append("Конкретные числа или локальные детали в prompt могут повторяться на каждом тайле.")

    return PreflightReport(
        tiles=tiles,
        estimated_output_bytes=estimated_output,
        estimated_temporary_bytes=estimated_temporary,
        required_free_bytes=required,
        available_free_bytes=available,
        estimated_ram_bytes=estimated_ram,
        available_ram_bytes=available_ram,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )
