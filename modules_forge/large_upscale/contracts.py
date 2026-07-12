from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


MANIFEST_VERSION = 1
JobStatus = Literal["created", "running", "cancelled", "failed", "completed"]


@dataclass(frozen=True)
class SourceAsset:
    path: str
    fingerprint: str
    width: int
    height: int
    format: str
    file_size: int
    mode: str
    orientation: int | None = None
    icc_profile_name: str | None = None
    has_icc: bool = False
    has_alpha: bool = False
    proxy_path: str | None = None

    @property
    def pixels(self) -> int:
        return self.width * self.height

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SourceAsset":
        return cls(**value)


@dataclass(frozen=True)
class TileRegion:
    index: int
    x: int
    y: int
    width: int
    height: int
    core_x: int
    core_y: int
    core_width: int
    core_height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


@dataclass(frozen=True)
class LargeUpscaleJobSpec:
    job_id: str
    source: SourceAsset
    target_width: int
    target_height: int
    prompt: str
    negative_prompt: str = ""
    analysis_profile: str = ""
    profile: str = "detail"
    denoising_strength: float = 0.35
    sampler_name: str | None = None
    scheduler: str | None = None
    steps: int = 24
    cfg_scale: float = 6.0
    distilled_cfg_scale: float = 3.0
    seed: int = -1
    batch_size: int = 1
    tile_width: int = 1024
    tile_height: int = 1024
    overlap: int = 128
    seam_blending: str = "cosine"
    upscaler_name: str = "Lanczos"
    vae_tiling: bool = True
    output_path: str = ""
    output_format: str = "png"
    jpeg_quality: int = 90
    webp_lossless: bool = False
    keep_metadata: bool = True
    keep_icc: bool = True
    keep_alpha: bool = True
    resume_enabled: bool = True
    cleanup_after_success: bool = True
    keep_temp_on_error: bool = True
    temp_root: str = ""
    assembly_block_size: int = 2048
    proxy_max_side: int = 2048
    proxy_max_payload_bytes: int = 12 * 1024 * 1024
    checkpoint: str | None = None
    additional_modules: tuple[str, ...] = ()
    model_preset: str = "sd"

    def __post_init__(self) -> None:
        object.__setattr__(self, "additional_modules", tuple(self.additional_modules))

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "LargeUpscaleJobSpec":
        data = dict(value)
        data["source"] = SourceAsset.from_dict(data["source"])
        data["additional_modules"] = tuple(data.get("additional_modules", ()))
        return cls(**data)


@dataclass
class LargeUpscaleManifest:
    spec: LargeUpscaleJobSpec
    tiles: list[TileRegion]
    status: JobStatus = "created"
    completed_tiles: list[int] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    working_directory: str = ""
    working_raster: str = ""
    result_path: str | None = None
    proxy_path: str | None = None
    error: str | None = None
    version: int = MANIFEST_VERSION

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "LargeUpscaleManifest":
        if value.get("version") != MANIFEST_VERSION:
            raise ValueError(f"Неподдерживаемая версия manifest: {value.get('version')}")
        data = dict(value)
        data["spec"] = LargeUpscaleJobSpec.from_dict(data["spec"])
        data["tiles"] = [TileRegion(**tile) for tile in data["tiles"]]
        return cls(**data)

    @classmethod
    def load(cls, path: str | Path) -> "LargeUpscaleManifest":
        with Path(path).open("r", encoding="utf-8") as handle:
            return cls.from_dict(json.load(handle))


@dataclass(frozen=True)
class LargeUpscaleResult:
    path: str
    proxy_path: str
    width: int
    height: int
    format: str
    file_size: int
    infotext: str
    manifest_path: str
