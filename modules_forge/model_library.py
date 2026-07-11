from __future__ import annotations

import os
import subprocess
from pathlib import Path

import gradio as gr

from modules import paths


LIBRARY_FOLDERS = (
    ("Stable-diffusion", ("Stable-diffusion", "Stable Diffusion", "checkpoints", "Checkpoint")),
    ("VAE", ("VAE", "vae")),
    ("text_encoder", ("text_encoder", "Text Encoder", "text-encoder")),
    ("Lora", ("Lora", "LoRA", "lora")),
    ("ESRGAN", ("ESRGAN", "Upscalers", "upscalers")),
    ("ControlNet", ("ControlNet", "controlnet")),
    ("embeddings", ("embeddings", "Embeddings")),
)
LINK_NAME = "Atlas Library"


def choose_library_folder(current_path: str = "") -> tuple[str, str]:
    """Open a native folder picker on the local Forge machine."""
    try:
        from tkinter import Tk, filedialog

        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(
            initialdir=current_path if os.path.isdir(current_path) else str(Path(paths.models_path).parent),
            title="Выбери общую папку с моделями",
        )
        root.destroy()
    except Exception as error:
        return current_path, f"Не удалось открыть выбор папки: {error}"

    return (selected or current_path), ("Папка выбрана." if selected else "Выбор папки отменён.")


def _library_folder(root: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        candidate = root / name
        if candidate.is_dir():
            return candidate
    return None


def _create_directory_link(source: Path, destination: Path) -> None:
    source = source.resolve()
    destination = destination.resolve()
    if os.name == "nt":
        source_literal = str(source).replace("'", "''")
        destination_literal = str(destination).replace("'", "''")
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                f"New-Item -ItemType Junction -Path '{destination_literal}' -Target '{source_literal}' -ErrorAction Stop | Out-Null",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout).strip() or "Windows не создала ссылку на папку.")
    else:
        os.symlink(source, destination, target_is_directory=True)


def connect_library(library_path: str) -> tuple[str, list[str], list[str]]:
    """Link conventional folders from an external model library without copying files."""
    if not library_path:
        return "Сначала выбери папку с моделями.", [], []

    library_root = Path(library_path).expanduser().resolve()
    atlas_models = Path(paths.models_path).resolve()
    if not library_root.is_dir():
        return "Указанная папка не существует или недоступна.", [], []
    if library_root == atlas_models or atlas_models in library_root.parents:
        return "Выбери внешнюю папку с моделями, а не папку моделей самого Forge Atlas.", [], []

    connected, skipped = [], []
    for target_name, source_names in LIBRARY_FOLDERS:
        source = _library_folder(library_root, source_names)
        if source is None:
            continue

        target = atlas_models / target_name
        target.mkdir(parents=True, exist_ok=True)
        link = target / LINK_NAME
        if os.path.lexists(link):
            skipped.append(target_name)
            continue

        try:
            _create_directory_link(source, link)
            connected.append(target_name)
        except Exception as error:
            return f"Не удалось подключить «{target_name}»: {error}", [], []

    if not connected:
        if skipped:
            return "Эта библиотека уже подключена. Удалять или заменять существующие ссылки автоматически Atlas не будет.", [], []
        return "В выбранной папке не найдены привычные каталоги моделей: Stable-diffusion, VAE, Lora, ESRGAN и другие.", [], []

    from modules import sd_models, sd_vae
    from modules_forge import main_entry

    sd_models.list_models()
    sd_vae.refresh_vae_list()
    checkpoints, modules = main_entry.refresh_models()
    detail = ", ".join(connected)
    return f"Подключено без копирования: {detail}. Теперь выбери checkpoint в верхней строке.", checkpoints, modules


def create_startup_dialog() -> dict[str, gr.components.Component]:
    from modules import sd_models

    no_checkpoints = not sd_models.checkpoints_list
    with gr.Column(visible=no_checkpoints, elem_id="atlas_model_library_dialog") as dialog:
        with gr.Column(elem_id="atlas_model_library_card"):
            gr.HTML("<h2>Модели пока не найдены</h2><p>Выбери общую папку, где уже лежат твои модели. Forge Atlas подключит знакомые папки ссылками — ничего копировать не будет.</p>")
            with gr.Row():
                choose = gr.Button("Выбрать", variant="primary")
                continue_without = gr.Button("Продолжить без моделей", variant="secondary")
            status = gr.Markdown("После подключения выбери модель в верхней строке.", elem_id="atlas_model_library_status")

    return {
        "dialog": dialog,
        "choose": choose,
        "continue": continue_without,
        "status": status,
    }


def bind_startup_dialog(dialog: dict[str, gr.components.Component], checkpoint_dropdown, modules_dropdown) -> None:
    def choose_and_connect():
        path, picker_message = choose_library_folder()
        if not path:
            return picker_message, gr.update(visible=True), gr.skip(), gr.skip()

        message, checkpoints, modules = connect_library(path)
        close = bool(checkpoints)
        return message, gr.update(visible=not close), gr.update(choices=checkpoints), gr.update(choices=modules)

    dialog["choose"].click(
        fn=choose_and_connect,
        outputs=[dialog["status"], dialog["dialog"], checkpoint_dropdown, modules_dropdown],
        queue=False,
        show_progress=False,
    )
    dialog["continue"].click(
        fn=lambda: gr.update(visible=False),
        outputs=[dialog["dialog"]],
        queue=False,
        show_progress=False,
    )
