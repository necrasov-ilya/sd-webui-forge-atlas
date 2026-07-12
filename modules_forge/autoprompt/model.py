from __future__ import annotations

import gc
import threading
import time
from pathlib import Path

from PIL import Image

from modules import paths
from modules_forge.autoprompt.compiler import compile_tile_safe_prompt
from modules_forge.autoprompt.download import validate_florence_directory


STYLE_REQUEST = (
    "Describe only the image's overall medium, broad scene category, composition, lighting, color palette, "
    "contrast, atmosphere, texture and global level of detail. Do not list people, objects, names, text, "
    "counts or local positions. The description must remain valid for every tile of the image."
)
FALLBACK_TASK = "<MORE_DETAILED_CAPTION>"
def florence_model_path(configured_path: str | None = None) -> Path:
    return Path(configured_path).expanduser().resolve() if configured_path else Path(paths.models_path).resolve() / "AutoPrompt" / "Florence-2-base-ft"


def florence_is_installed(configured_path: str | None = None) -> bool:
    return validate_florence_directory(florence_model_path(configured_path))[0]


class FlorenceService:
    """Lazy Florence cache. CPU is the default and never touches Forge's model state."""

    def __init__(self):
        self._lock = threading.RLock()
        self._model = None
        self._processor = None
        self._device = "cpu"
        self._path: Path | None = None
        self._last_used = 0.0
        self._unload_timer: threading.Timer | None = None

    def _load(self, model_path: Path, use_gpu: bool) -> tuple[object, object, str]:
        import torch

        from modules_forge.autoprompt.conversion import build_processor_and_config, load_converted_model

        valid, message = validate_florence_directory(model_path)
        if not valid:
            raise FileNotFoundError(message)
        device = "cuda" if use_gpu and torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32
        if self._model is not None and self._path == model_path and self._device == device:
            return self._model, self._processor, device
        self.unload()
        processor, config = build_processor_and_config(model_path, dtype)
        model = load_converted_model(model_path, config, len(processor.tokenizer), dtype).to(device)
        model.eval()
        self._model, self._processor, self._device, self._path = model, processor, device, model_path
        return model, processor, device

    def _generate(self, image: Image.Image, prompt: str, model_path: Path, use_gpu: bool) -> str:
        import torch

        model, processor, device = self._load(model_path, use_gpu)
        dtype = torch.float16 if device == "cuda" else torch.float32
        inputs = processor(text=prompt, images=image.convert("RGB"), return_tensors="pt")
        inputs = {key: value.to(device, dtype=dtype) if key == "pixel_values" else value.to(device) for key, value in inputs.items()}
        with torch.inference_mode():
            generated = model.generate(**inputs, max_new_tokens=192, num_beams=3, do_sample=False)
        return processor.batch_decode(generated, skip_special_tokens=True)[0].strip()

    def analyse(
        self,
        proxy_path: str | Path,
        *,
        configured_path: str | None = None,
        use_gpu: bool = False,
        max_prompt_length: int = 320,
        retention_minutes: int = 10,
    ) -> tuple[str, str, str]:
        model_path = florence_model_path(configured_path)
        with self._lock, Image.open(proxy_path) as image:
            try:
                try:
                    raw_caption = self._generate(image, STYLE_REQUEST, model_path, use_gpu)
                    profile = "tile-safe style analysis"
                except (ValueError, RuntimeError):
                    raw_caption = ""
                    profile = "official detailed caption fallback"
                if len(raw_caption.strip()) < 12:
                    raw_caption = self._generate(image, FALLBACK_TASK, model_path, use_gpu)
                    profile = "official detailed caption fallback"
            finally:
                self._last_used = time.monotonic()
                if self._unload_timer is not None:
                    self._unload_timer.cancel()
                self._unload_timer = threading.Timer(max(0, retention_minutes) * 60, self.unload_if_idle, args=(retention_minutes,))
                self._unload_timer.daemon = True
                self._unload_timer.start()
        return compile_tile_safe_prompt(raw_caption, max_prompt_length), raw_caption, profile

    def unload_if_idle(self, retention_minutes: int) -> bool:
        if retention_minutes < 0:
            return False
        with self._lock:
            if self._model is None or time.monotonic() - self._last_used < retention_minutes * 60:
                return False
            self.unload()
            return True

    def unload(self) -> None:
        with self._lock:
            model = self._model
            self._model = None
            self._processor = None
            self._path = None
            if self._unload_timer is not None:
                self._unload_timer.cancel()
                self._unload_timer = None
            if model is not None:
                del model
            gc.collect()
            if self._device == "cuda":
                try:
                    import torch

                    torch.cuda.empty_cache()
                except Exception:
                    pass
            self._device = "cpu"


service = FlorenceService()
