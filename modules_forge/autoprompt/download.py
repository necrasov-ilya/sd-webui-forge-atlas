from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
from pathlib import Path
from typing import Callable

import httpx
from safetensors import safe_open


FLORENCE_REPO = "microsoft/Florence-2-base-ft"
FLORENCE_REVISION = "f6c1a25888ffc1d945ee8a1a77ac833c7303d46e"
FLORENCE_LICENSE = "MIT"
FLORENCE_FILES = {
    "LICENSE": 1141,
    "config.json": 2430,
    "model.safetensors": 463_221_266,
    "preprocessor_config.json": 806,
    "tokenizer.json": 1_355_863,
    "tokenizer_config.json": 34,
    "vocab.json": 1_099_884,
}
FLORENCE_MODEL_SHA256 = "58757d657ff44051314c8030b68e04cb1bb618ca9a4885418f111f6fb708185a"
FLORENCE_TOTAL_BYTES = sum(FLORENCE_FILES.values())
INSTALL_MARKER = "atlas-install.json"


class DownloadCancelled(RuntimeError):
    pass


ProgressCallback = Callable[[int, int, str], None]


def _resolve_url(filename: str) -> str:
    return f"https://huggingface.co/{FLORENCE_REPO}/resolve/{FLORENCE_REVISION}/{filename}?download=true"


def _sha256(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def validate_florence_directory(path: str | Path, verify_hash: bool = False) -> tuple[bool, str]:
    directory = Path(path)
    if not directory.is_dir():
        return False, "Каталог модели отсутствует."
    for filename, expected_size in FLORENCE_FILES.items():
        candidate = directory / filename
        if not candidate.is_file():
            return False, f"Не хватает файла {filename}."
        if candidate.stat().st_size != expected_size:
            return False, f"Файл {filename} имеет неправильный размер."
    try:
        with safe_open(directory / "model.safetensors", framework="pt", device="cpu") as handle:
            if not handle.keys():
                return False, "model.safetensors не содержит тензоров."
    except Exception as error:
        return False, f"Не удалось проверить model.safetensors: {error}"
    if verify_hash and _sha256(directory / "model.safetensors") != FLORENCE_MODEL_SHA256:
        return False, "Контрольная сумма model.safetensors не совпала с официальной ревизией."
    return True, "Модель готова."


class FlorenceDownloader:
    def __init__(self):
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def reset(self) -> None:
        self._cancel.clear()

    def _check_cancel(self) -> None:
        if self._cancel.is_set():
            raise DownloadCancelled("Загрузка отменена. Уже скачанные части сохранены для продолжения.")

    def download(self, destination: str | Path, progress: ProgressCallback | None = None) -> Path:
        destination = Path(destination).expanduser().resolve()
        valid, _message = validate_florence_directory(destination)
        if valid:
            return destination
        if destination.exists():
            raise FileExistsError(f"Каталог {destination} уже существует, но не является готовой моделью Atlas. Его содержимое не изменено.")

        self.reset()
        staging = destination.parent / f".{destination.name}.download"
        staging.mkdir(parents=True, exist_ok=True)
        downloaded_before = sum((staging / name).stat().st_size for name in FLORENCE_FILES if (staging / name).is_file())
        required = max(0, FLORENCE_TOTAL_BYTES - downloaded_before) + 256 * 1024 * 1024
        available = shutil.disk_usage(staging).free
        if available < required:
            raise OSError(f"Недостаточно места для Florence: нужно не меньше {required} байт, доступно {available} байт.")
        completed = downloaded_before
        timeout = httpx.Timeout(connect=30, read=60, write=60, pool=30)
        try:
            with httpx.Client(follow_redirects=True, timeout=timeout, headers={"User-Agent": "Forge-Atlas/Florence-installer"}) as client:
                for filename, expected_size in FLORENCE_FILES.items():
                    self._check_cancel()
                    final_file = staging / filename
                    if final_file.is_file() and final_file.stat().st_size == expected_size:
                        if progress:
                            progress(completed, FLORENCE_TOTAL_BYTES, filename)
                        continue
                    partial = staging / f"{filename}.part"
                    offset = partial.stat().st_size if partial.is_file() else 0
                    headers = {"Range": f"bytes={offset}-"} if offset else {}
                    with client.stream("GET", _resolve_url(filename), headers=headers) as response:
                        response.raise_for_status()
                        append = offset > 0 and response.status_code == 206
                        if not append:
                            offset = 0
                        with partial.open("ab" if append else "wb") as handle:
                            for chunk in response.iter_bytes(1024 * 1024):
                                self._check_cancel()
                                handle.write(chunk)
                                if progress:
                                    progress(completed + offset + handle.tell() - (offset if append else 0), FLORENCE_TOTAL_BYTES, filename)
                            handle.flush()
                            os.fsync(handle.fileno())
                    if partial.stat().st_size != expected_size:
                        raise IOError(f"Файл {filename} скачан не полностью: {partial.stat().st_size} из {expected_size} байт.")
                    os.replace(partial, final_file)
                    completed += expected_size
        except httpx.HTTPError as error:
            raise ConnectionError(f"Не удалось скачать Florence с Hugging Face: {error}") from error

        valid, message = validate_florence_directory(staging, verify_hash=True)
        if not valid:
            raise IOError(message)
        marker = {
            "repository": FLORENCE_REPO,
            "revision": FLORENCE_REVISION,
            "license": FLORENCE_LICENSE,
            "files": FLORENCE_FILES,
            "model_sha256": FLORENCE_MODEL_SHA256,
        }
        (staging / INSTALL_MARKER).write_text(json.dumps(marker, ensure_ascii=False, indent=2), encoding="utf-8")
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, destination)
        return destination
