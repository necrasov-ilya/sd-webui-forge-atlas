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

from modules import paths
from modules_forge.model_components.registry import COMPONENTS, ComponentSpec


ProgressCallback = Callable[[int, int, str], None]


class ComponentDownloadCancelled(RuntimeError):
    pass


def component_destination(spec: ComponentSpec) -> Path:
    folder = "VAE" if spec.kind == "vae" else "text_encoder"
    return Path(paths.models_path) / folder / spec.filename


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def validate_component(path: Path, spec: ComponentSpec, verify_hash: bool = True) -> tuple[bool, str]:
    if not path.is_file() or path.stat().st_size != spec.size:
        return False, f"{spec.filename}: неправильный размер или файл отсутствует."
    try:
        with safe_open(path, framework="pt", device="cpu") as handle:
            if not list(handle.keys()):
                return False, f"{spec.filename}: safetensors не содержит тензоров."
    except Exception as error:
        return False, f"{spec.filename}: не удалось проверить safetensors ({error})."
    if verify_hash and _sha256(path) != spec.sha256:
        return False, f"{spec.filename}: SHA-256 не совпадает с зафиксированным источником."
    return True, "Готово."


class ComponentDownloader:
    def __init__(self):
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def _check_cancel(self) -> None:
        if self._cancel.is_set():
            raise ComponentDownloadCancelled("Загрузка отменена. Частично скачанные файлы сохранены для продолжения.")

    def download(self, component_ids: list[str] | tuple[str, ...], progress: ProgressCallback | None = None) -> list[Path]:
        specs = [COMPONENTS[item] for item in component_ids]
        self._cancel.clear()
        staging = Path(paths.models_path) / ".atlas-component-downloads"
        staging.mkdir(parents=True, exist_ok=True)
        required = sum(spec.size for spec in specs if not validate_component(component_destination(spec), spec, verify_hash=False)[0])
        if shutil.disk_usage(staging).free < required + 256 * 1024 * 1024:
            raise OSError(f"Недостаточно места: для компонентов и безопасной финализации нужно не меньше {required + 256 * 1024 * 1024} байт.")

        completed = 0
        installed: list[Path] = []
        timeout = httpx.Timeout(connect=30, read=90, write=90, pool=30)
        with httpx.Client(follow_redirects=True, timeout=timeout, headers={"User-Agent": "Forge-Atlas/component-installer"}) as client:
            for spec in specs:
                destination = component_destination(spec)
                valid, _ = validate_component(destination, spec)
                if valid:
                    completed += spec.size
                    installed.append(destination)
                    continue
                if destination.exists():
                    raise FileExistsError(f"{destination} уже существует, но не совпадает с зафиксированным компонентом. Atlas не будет заменять его автоматически.")

                partial = staging / f"{spec.filename}.part"
                offset = partial.stat().st_size if partial.is_file() else 0
                if offset > spec.size:
                    partial.unlink()
                    offset = 0
                headers = {"Range": f"bytes={offset}-"} if offset else {}
                self._check_cancel()
                try:
                    with client.stream("GET", spec.source_url, headers=headers) as response:
                        response.raise_for_status()
                        append = offset > 0 and response.status_code == 206
                        if not append:
                            offset = 0
                        with partial.open("ab" if append else "wb") as handle:
                            for chunk in response.iter_bytes(1024 * 1024):
                                self._check_cancel()
                                handle.write(chunk)
                                if progress:
                                    progress(completed + handle.tell(), sum(item.size for item in specs), spec.filename)
                            handle.flush()
                            os.fsync(handle.fileno())
                except httpx.HTTPError as error:
                    raise ConnectionError(f"Не удалось скачать {spec.filename}: {error}") from error
                if partial.stat().st_size != spec.size:
                    raise IOError(f"{spec.filename} скачан не полностью: {partial.stat().st_size} из {spec.size} байт.")
                valid, message = validate_component(partial, spec)
                if not valid:
                    raise IOError(message)
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(partial, destination)
                completed += spec.size
                installed.append(destination)

        marker_path = Path(paths.models_path) / ".atlas-components.json"
        existing = json.loads(marker_path.read_text(encoding="utf-8")) if marker_path.is_file() else {}
        for spec in specs:
            existing[spec.id] = {"repository": spec.repository, "revision": spec.revision, "path": spec.repository_path, "sha256": spec.sha256, "destination": str(component_destination(spec))}
        temporary = marker_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, marker_path)
        return installed
