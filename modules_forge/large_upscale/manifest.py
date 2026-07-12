from __future__ import annotations

import os
import tempfile
from pathlib import Path

from modules_forge.large_upscale.contracts import LargeUpscaleManifest


def save_manifest(manifest: LargeUpscaleManifest, path: str | Path) -> None:
    destination = Path(path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(manifest.to_json())
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
