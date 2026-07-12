from __future__ import annotations

import binascii
import mmap
import os
import struct
import tempfile
import zlib
from pathlib import Path

import numpy as np
from PIL import Image


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def create_raster(path: str | Path, width: int, height: int, channels: int = 3) -> np.memmap:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    return np.memmap(destination, dtype=np.uint8, mode="w+", shape=(height, width, channels))


def open_raster(path: str | Path, width: int, height: int, channels: int = 3, mode: str = "r+") -> np.memmap:
    return np.memmap(Path(path), dtype=np.uint8, mode=mode, shape=(height, width, channels))


def _png_chunk(handle, kind: bytes, payload: bytes) -> None:
    handle.write(struct.pack(">I", len(payload)))
    handle.write(kind)
    handle.write(payload)
    handle.write(struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF))


def write_png_streaming(
    raster: np.ndarray,
    destination: str | Path,
    *,
    infotext: str = "",
    icc_profile: bytes | None = None,
    exif_bytes: bytes | None = None,
    rows_per_chunk: int = 32,
) -> None:
    """Write RGB/RGBA scanlines without constructing a full PIL image."""
    height, width, channels = raster.shape
    if channels not in {3, 4}:
        raise ValueError("PNG exporter supports only RGB and RGBA rasters.")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(PNG_SIGNATURE)
            color_type = 6 if channels == 4 else 2
            _png_chunk(handle, b"IHDR", struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0))
            if icc_profile:
                _png_chunk(handle, b"iCCP", b"ICC Profile\x00\x00" + zlib.compress(icc_profile, 6))
            if infotext:
                payload = b"parameters\x00\x00\x00\x00\x00" + infotext.encode("utf-8")
                _png_chunk(handle, b"iTXt", payload)
            if exif_bytes:
                payload = exif_bytes[6:] if exif_bytes.startswith(b"Exif\x00\x00") else exif_bytes
                _png_chunk(handle, b"eXIf", payload)

            compressor = zlib.compressobj(level=6)
            pending = bytearray()
            for start in range(0, height, rows_per_chunk):
                stop = min(height, start + rows_per_chunk)
                block = np.ascontiguousarray(raster[start:stop])
                filtered = b"".join(b"\x00" + block[row].tobytes() for row in range(block.shape[0]))
                pending.extend(compressor.compress(filtered))
                if len(pending) >= 1024 * 1024:
                    _png_chunk(handle, b"IDAT", bytes(pending))
                    pending.clear()
            pending.extend(compressor.flush())
            if pending:
                _png_chunk(handle, b"IDAT", bytes(pending))
            _png_chunk(handle, b"IEND", b"")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def write_pillow_from_mmap(
    raster_path: str | Path,
    width: int,
    height: int,
    destination: str | Path,
    image_format: str,
    *,
    channels: int = 3,
    quality: int = 90,
    lossless: bool = False,
    icc_profile: bytes | None = None,
    exif_bytes: bytes | None = None,
) -> None:
    """Give Pillow a memory-mapped backing store instead of a copied RGB buffer."""
    source = Path(raster_path)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    os.close(descriptor)
    try:
        with source.open("rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
            mode = "RGBA" if channels == 4 else "RGB"
            image = Image.frombuffer(mode, (width, height), mapped, "raw", mode, 0, 1)
            options = {"quality": quality}
            if image_format.upper() == "WEBP":
                options["lossless"] = lossless
            if icc_profile:
                options["icc_profile"] = icc_profile
            if exif_bytes:
                options["exif"] = exif_bytes
            image.save(temporary, format=image_format.upper(), **options)
            image.close()
        os.replace(temporary, destination)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def create_proxy_from_raster(raster: np.ndarray, destination: str | Path, max_side: int = 2048, max_payload_bytes: int = 12 * 1024 * 1024) -> str:
    height, width, _channels = raster.shape
    scale = min(1.0, max_side / max(width, height))
    proxy_width = max(1, round(width * scale))
    proxy_height = max(1, round(height * scale))
    xs = np.linspace(0, width - 1, proxy_width, dtype=np.int64)
    ys = np.linspace(0, height - 1, proxy_height, dtype=np.int64)
    # Advanced indexing allocates only the bounded proxy, never the full raster.
    sampled = np.ascontiguousarray(raster[np.ix_(ys, xs)])
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    mode = "RGBA" if sampled.shape[2] == 4 else "RGB"
    image = Image.fromarray(sampled, mode=mode)
    quality = 88
    while True:
        image.save(destination, format="WEBP", quality=quality, method=4)
        if destination.stat().st_size <= max_payload_bytes:
            break
        if max(image.size) <= 512 and quality <= 45:
            image.close()
            raise ValueError("Не удалось уложить proxy результата в заданный предел payload.")
        if quality <= 55:
            image.thumbnail((max(512, int(image.width * 0.8)), max(512, int(image.height * 0.8))), Image.Resampling.LANCZOS)
            quality = 76
        else:
            quality -= 10
    image.close()
    return str(destination)
