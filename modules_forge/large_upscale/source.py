from __future__ import annotations

import hashlib
import os
import tempfile
import threading
from pathlib import Path

from PIL import Image, ImageCms, ImageOps

from modules_forge.large_upscale.contracts import SourceAsset


SUPPORTED_SOURCE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".avif", ".heif", ".jxl")
_pillow_limit_lock = threading.Lock()


def open_local_image(path: str | Path) -> Image.Image:
    """Open a user-selected local file without Pillow's arbitrary pixel ceiling."""
    with _pillow_limit_lock:
        previous_limit = Image.MAX_IMAGE_PIXELS
        Image.MAX_IMAGE_PIXELS = None
        try:
            return Image.open(path)
        finally:
            Image.MAX_IMAGE_PIXELS = previous_limit


def random_access_backend_available() -> bool:
    try:
        import pyvips  # noqa: F401

        return True
    except Exception:
        return False


def choose_source_image(current_path: str = "") -> str:
    """Open the native picker on the machine where Forge is running."""
    from tkinter import Tk, filedialog

    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askopenfilename(
            initialdir=str(Path(current_path).parent) if current_path else str(Path.home()),
            title="Выбери изображение",
            filetypes=[("Изображения", " ".join(f"*{ext}" for ext in SUPPORTED_SOURCE_EXTENSIONS)), ("Все файлы", "*.*")],
        )
    finally:
        root.destroy()
    return selected or current_path


def source_fingerprint(path: str | Path, sample_size: int = 64 * 1024) -> str:
    source = Path(path).resolve()
    stat = source.stat()
    digest = hashlib.sha256()
    digest.update(str(source).encode("utf-8", errors="surrogatepass"))
    digest.update(f"|{stat.st_size}|{stat.st_mtime_ns}|".encode())
    with source.open("rb") as handle:
        digest.update(handle.read(sample_size))
        if stat.st_size > sample_size:
            handle.seek(max(0, stat.st_size - sample_size))
            digest.update(handle.read(sample_size))
    return digest.hexdigest()


def _profile_name(profile: bytes | None) -> str | None:
    if not profile:
        return None
    try:
        return ImageCms.getProfileName(ImageCms.ImageCmsProfile(profile)).strip()
    except Exception:
        return "Встроенный ICC-профиль"


def _bound_proxy_payload(destination: Path, max_payload_bytes: int) -> None:
    quality = 82
    while destination.stat().st_size > max_payload_bytes:
        with open_local_image(destination) as opened:
            image = opened.copy()
        if max(image.size) <= 512 and quality <= 45:
            raise ValueError("Не удалось уложить proxy в заданный предел payload.")
        if quality <= 55:
            image.thumbnail((max(512, int(image.width * 0.8)), max(512, int(image.height * 0.8))), Image.Resampling.LANCZOS)
            quality = 76
        image.save(destination, format="WEBP", quality=quality, method=4)
        image.close()
        quality -= 10


def create_proxy(source_path: str | Path, destination: str | Path, max_side: int = 2048, max_payload_bytes: int = 12 * 1024 * 1024) -> str:
    if max_side < 256:
        raise ValueError("Размер proxy должен быть не меньше 256 px.")

    source_path = Path(source_path).resolve()
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        import pyvips

        image = pyvips.Image.new_from_file(str(source_path), access="sequential").autorot()
        scale = min(1.0, max_side / max(image.width, image.height))
        proxy = image.resize(scale) if scale < 1 else image
        proxy.write_to_file(str(destination), Q=88, strip=True)
        _bound_proxy_payload(destination, max_payload_bytes)
        return str(destination)
    except Exception as vips_error:
        # Pillow remains a fallback for ordinary images and minimal installs,
        # but never silently full-decodes an ultra-large file after libvips fails.
        with open_local_image(source_path) as metadata_only:
            if metadata_only.width * metadata_only.height > 250_000_000:
                raise RuntimeError(f"libvips не смог безопасно создать proxy большого исходника: {vips_error}") from vips_error

    with open_local_image(source_path) as opened:
        # JPEG draft asks the decoder for a bounded lower-resolution representation.
        if (opened.format or "").upper() in {"JPEG", "MPO"}:
            ratio = max(opened.width / max_side, opened.height / max_side, 1)
            opened.draft("RGB", (max(1, int(opened.width / ratio)), max(1, int(opened.height / ratio))))
        image = ImageOps.exif_transpose(opened)
        image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS, reducing_gap=3.0)
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        image.save(destination, format="WEBP", quality=88, method=4)
    _bound_proxy_payload(destination, max_payload_bytes)
    return str(destination)


def inspect_source(path: str | Path, proxy_max_side: int = 2048, proxy_dir: str | Path | None = None, proxy_max_payload_bytes: int = 12 * 1024 * 1024) -> SourceAsset:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Исходник недоступен: {source}")
    if source.suffix.lower() not in SUPPORTED_SOURCE_EXTENSIONS:
        raise ValueError(f"Формат {source.suffix or 'без расширения'} пока не поддерживается.")

    fingerprint = source_fingerprint(source)
    proxy_root = Path(proxy_dir) if proxy_dir else Path(tempfile.gettempdir()) / "forge-atlas" / "proxies"
    proxy_path = proxy_root / f"{fingerprint[:20]}.webp"

    with open_local_image(source) as image:
        exif = image.getexif()
        orientation = exif.get(274) if exif else None
        width, height = image.size
        if orientation in {5, 6, 7, 8}:
            width, height = height, width
        icc_profile = image.info.get("icc_profile")
        asset = SourceAsset(
            path=str(source),
            fingerprint=fingerprint,
            width=width,
            height=height,
            format=(image.format or source.suffix.lstrip(".")).upper(),
            file_size=source.stat().st_size,
            mode=image.mode,
            orientation=orientation,
            icc_profile_name=_profile_name(icc_profile),
            has_icc=bool(icc_profile),
            has_alpha="A" in image.getbands() or "transparency" in image.info,
            proxy_path=str(proxy_path),
        )

    if not proxy_path.is_file() or proxy_path.stat().st_size > proxy_max_payload_bytes:
        create_proxy(source, proxy_path, proxy_max_side, proxy_max_payload_bytes)
    return asset


def source_is_unchanged(asset: SourceAsset) -> bool:
    try:
        return source_fingerprint(asset.path) == asset.fingerprint
    except OSError:
        return False


def format_file_size(value: int) -> str:
    size = float(value)
    for suffix in ("Б", "КиБ", "МиБ", "ГиБ", "ТиБ"):
        if size < 1024 or suffix == "ТиБ":
            return f"{size:.1f} {suffix}" if suffix != "Б" else f"{int(size)} {suffix}"
        size /= 1024
    return f"{value} Б"


def describe_source(asset: SourceAsset) -> str:
    flags = []
    if asset.has_icc:
        flags.append(asset.icc_profile_name or "ICC")
    if asset.has_alpha:
        flags.append("alpha")
    if asset.orientation and asset.orientation != 1:
        flags.append(f"ориентация EXIF {asset.orientation}")
    suffix = f" · {' · '.join(flags)}" if flags else ""
    return f"**{asset.width} × {asset.height}** · {asset.format} · {format_file_size(asset.file_size)}{suffix}\n\n`{asset.path}`"
