from __future__ import annotations

import os
import subprocess
from pathlib import Path

import gradio as gr

from modules import paths
from modules_forge.autoprompt.download import FLORENCE_LICENSE, FLORENCE_REPO, FLORENCE_REVISION, FLORENCE_TOTAL_BYTES, FlorenceDownloader
from modules_forge.autoprompt.model import florence_is_installed, florence_model_path
from modules_forge.large_upscale.source import format_file_size


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
MODEL_FILE_EXTENSIONS = {".ckpt", ".pt", ".pth", ".bin", ".safetensors", ".sft", ".gguf"}
florence_downloader = FlorenceDownloader()


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
    counts: dict[str, int] = {}
    for target_name, source_names in LIBRARY_FOLDERS:
        source = _library_folder(library_root, source_names)
        if source is None:
            continue

        counts[target_name] = sum(1 for item in source.rglob("*") if item.is_file() and item.suffix.lower() in MODEL_FILE_EXTENSIONS)

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
    report = " · ".join(f"{name}: {count}" for name, count in counts.items())
    return (
        f"Подключено без копирования: {detail}. Найдено файлов: {report}. "
        "Отдельные VAE и text encoder могут отсутствовать — они часто встроены в checkpoint.",
        checkpoints,
        modules,
    )


def create_startup_dialog() -> dict[str, gr.components.Component]:
    from modules import sd_models, shared

    no_checkpoints = not sd_models.checkpoints_list
    no_florence = not florence_is_installed() and not shared.opts.atlas_autoprompt_onboarding_dismissed
    with gr.Column(visible=no_checkpoints or no_florence, elem_id="atlas_model_library_dialog") as dialog:
        with gr.Column(elem_id="atlas_model_library_card"):
            with gr.Column(visible=no_checkpoints) as model_stage:
                gr.HTML("<h2>Модели пока не найдены</h2><p>Выбери общую папку, где уже лежат твои модели. Forge Atlas подключит знакомые папки ссылками — ничего копировать не будет.</p>")
                with gr.Row():
                    choose = gr.Button("Выбрать", variant="primary")
                    continue_without = gr.Button("Продолжить без моделей", variant="secondary")
            with gr.Column(visible=(not no_checkpoints) and no_florence) as florence_stage:
                gr.Markdown(
                    f"## Модель для Autoprompt\n\nОфициальный источник: **[{FLORENCE_REPO}](https://huggingface.co/{FLORENCE_REPO}/tree/{FLORENCE_REVISION})** · revision `{FLORENCE_REVISION}` · "
                    f"лицензия **[{FLORENCE_LICENSE}](https://huggingface.co/{FLORENCE_REPO}/blob/{FLORENCE_REVISION}/LICENSE)** · загрузка **{format_file_size(FLORENCE_TOTAL_BYTES)}**.\n\n"
                    f"Каталог: `{florence_model_path()}`. Atlas скачает только safetensors и необходимые настройки. "
                    "По умолчанию модель работает на CPU и не занимает VRAM Forge."
                )
                with gr.Row():
                    download_florence = gr.Button("Скачать модель", variant="primary")
                    skip_florence = gr.Button("Не сейчас", variant="secondary")
            initial_status = "После подключения выбери checkpoint в карточке «Модель»." if no_checkpoints else "Установка необязательна: можно продолжить и вернуться к ней позже."
            status = gr.Markdown(initial_status, elem_id="atlas_model_library_status")

    return {
        "dialog": dialog,
        "choose": choose,
        "continue": continue_without,
        "model_stage": model_stage,
        "florence_stage": florence_stage,
        "download_florence": download_florence,
        "skip_florence": skip_florence,
        "status": status,
    }


def bind_startup_dialog(dialog: dict[str, gr.components.Component], checkpoint_dropdown, modules_dropdown) -> None:
    from modules import shared

    def should_offer_florence() -> bool:
        return not florence_is_installed() and not shared.opts.atlas_autoprompt_onboarding_dismissed

    def choose_and_connect():
        path, picker_message = choose_library_folder()
        if not path:
            return picker_message, gr.update(visible=True), gr.update(visible=True), gr.update(visible=False), gr.skip(), gr.skip()

        message, checkpoints, modules = connect_library(path)
        connected = bool(checkpoints)
        show_florence = connected and should_offer_florence()
        return (
            message,
            gr.update(visible=not connected or show_florence),
            gr.update(visible=not connected),
            gr.update(visible=show_florence),
            gr.update(choices=checkpoints),
            gr.update(choices=modules),
        )

    dialog["choose"].click(
        fn=choose_and_connect,
        outputs=[dialog["status"], dialog["dialog"], dialog["model_stage"], dialog["florence_stage"], checkpoint_dropdown, modules_dropdown],
        queue=False,
        show_progress=False,
    )
    dialog["continue"].click(
        fn=lambda: (
            "Diffusion-модели можно подключить позже. Модель Autoprompt тоже необязательна.",
            gr.update(visible=False),
            gr.update(visible=should_offer_florence()),
            gr.update(visible=should_offer_florence()),
        ),
        outputs=[dialog["status"], dialog["model_stage"], dialog["florence_stage"], dialog["dialog"]],
        queue=False,
        show_progress=False,
    )

    def download_model(progress=gr.Progress()):
        def update(downloaded: int, total: int, filename: str):
            progress(downloaded / max(1, total), desc=f"{filename}: {format_file_size(downloaded)} из {format_file_size(total)}")

        florence_downloader.download(florence_model_path(), update)
        return "Florence установлена. Autoprompt готов к работе.", gr.update(visible=False)

    dialog["download_florence"].click(
        fn=download_model,
        outputs=[dialog["status"], dialog["dialog"]],
        show_progress=True,
    )
    dialog["skip_florence"].click(
        fn=lambda: _dismiss_florence_onboarding(shared),
        outputs=[dialog["status"], dialog["dialog"]],
        queue=False,
        show_progress=False,
    )


def _dismiss_florence_onboarding(shared):
    florence_downloader.cancel()
    shared.opts.set("atlas_autoprompt_onboarding_dismissed", True)
    shared.opts.save(shared.config_filename)
    return "Autoprompt можно установить позже в его вкладке.", gr.update(visible=False)
