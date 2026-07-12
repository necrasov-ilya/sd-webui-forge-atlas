from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import torch
from safetensors import safe_open

from modules_forge.model_components.registry import COMPONENTS, COMPONENT_ALIASES, FAMILY_BUNDLES, ComponentSpec, FamilyBundle


@dataclass(frozen=True)
class CheckpointInspection:
    path: str
    recognized: bool
    repository: str | None
    preset: str | None
    family_label: str
    embedded: tuple[str, ...]
    installed: tuple[str, ...]
    missing: tuple[str, ...]
    message: str

    @property
    def missing_specs(self) -> tuple[ComponentSpec, ...]:
        return tuple(COMPONENTS[item] for item in self.missing)


def _empty(path: str, message: str) -> CheckpointInspection:
    return CheckpointInspection(path, False, None, None, "Неизвестная модель", (), (), (), message)


def _read_safetensors_structure(path: str) -> tuple[dict[str, torch.Tensor], dict[str, str]]:
    with safe_open(path, framework="pt", device="cpu") as handle:
        tensors = {key: torch.empty(tuple(handle.get_slice(key).get_shape()), device="meta") for key in handle.keys()}
        metadata = handle.metadata() or {}
    return tensors, metadata


def _guess_bundle(tensors: dict[str, torch.Tensor]) -> FamilyBundle | None:
    from modules_forge.packages import huggingface_guess

    guessed = huggingface_guess.guess(tensors)
    return FAMILY_BUNDLES.get(guessed.huggingface_repo)


def _is_embedded(keys: tuple[str, ...], spec: ComponentSpec) -> bool:
    return any(any(key.startswith(marker) for marker in spec.embedded_markers) for key in keys)


def inspect_checkpoint(path: str, installed_modules: list[str] | tuple[str, ...] = ()) -> CheckpointInspection:
    candidate = Path(path)
    if not candidate.is_file():
        return _empty(path, "Выбранный checkpoint недоступен.")
    if candidate.suffix.lower() not in {".safetensors", ".sft"}:
        return _empty(path, "Автоматический разбор состава пока выполняется только для safetensors; тип модели можно выбрать вручную.")

    try:
        tensors, _metadata = _read_safetensors_structure(str(candidate))
        bundle = _guess_bundle(tensors)
    except Exception as error:
        return _empty(path, f"Forge не смог надёжно определить архитектуру: {error}")
    if bundle is None:
        return _empty(path, "Архитектура распознана Forge, но для неё ещё не зафиксирован комплект компонентов Atlas.")

    keys = tuple(tensors)
    available_names = {os.path.basename(value).casefold() for value in installed_modules}
    embedded, installed, missing = [], [], []
    for component_id in bundle.component_ids:
        spec = COMPONENTS[component_id]
        if _is_embedded(keys, spec):
            embedded.append(component_id)
        elif any(name.casefold() in available_names for name in COMPONENT_ALIASES.get(component_id, (spec.filename,))):
            installed.append(component_id)
        else:
            missing.append(component_id)

    if missing:
        labels = ", ".join(f"`{COMPONENTS[item].label}`" for item in missing)
        message = f"**{bundle.label}** · не хватает: {labels}."
    elif embedded and not installed:
        message = f"**{bundle.label}** · необходимые компоненты встроены в checkpoint."
    else:
        message = f"**{bundle.label}** · комплект компонентов готов."
    return CheckpointInspection(
        str(candidate.resolve()),
        True,
        bundle.repository,
        bundle.preset,
        bundle.label,
        tuple(embedded),
        tuple(installed),
        tuple(missing),
        message,
    )
