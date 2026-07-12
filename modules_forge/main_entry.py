import logging
import os.path

import gradio as gr
import torch
from gradio.context import Context
from rich import print_json

from backend import memory_management
from backend.args import dynamic_args
from backend.logging import setup_logger
from modules import (
    infotext_utils,
    paths,
    processing,
    sd_models,
    shared,
    shared_items,
    ui_common,
)
from modules_forge.presets import PresetArch, is_video, use_distill, use_shift
from modules_forge.model_components.download import ComponentDownloader, component_destination
from modules_forge.model_components.inspector import inspect_checkpoint
from modules_forge.model_components.registry import COMPONENTS

logger = logging.getLogger("ui_models")
setup_logger(logger)

ui_forge_preset: gr.Radio
ui_checkpoint: gr.Dropdown
ui_vae: gr.Dropdown
ui_forge_unet_dtype: gr.Radio
component_downloader = ComponentDownloader()

forge_unet_storage_dtype_options: dict[str, tuple[torch.dtype, bool]] = {
    "Automatic": (None, False),
    "Automatic (fp16 LoRA)": (None, True),
    "float8-e4m3fn": (torch.float8_e4m3fn, False),
    "float8-e4m3fn (fp16 LoRA)": (torch.float8_e4m3fn, True),
    "float8-e5m2": (torch.float8_e5m2, False),
    "float8-e5m2 (fp16 LoRA)": (torch.float8_e5m2, True),
}

if memory_management.bnb_enabled():
    forge_unet_storage_dtype_options.update(
        {
            "bnb-nf4": ("nf4", False),
            "bnb-nf4 (fp16 LoRA)": ("nf4", True),
            "bnb-fp4": ("fp4", False),
            "bnb-fp4 (fp16 LoRA)": ("fp4", True),
        }
    )


module_list: dict[str, os.PathLike] = {}


def _component_module_values(inspection, preset: str) -> list[str]:
    from modules_forge.model_components.registry import COMPONENT_ALIASES

    values = {os.path.basename(item) for item in getattr(shared.opts, f"forge_additional_modules_{preset}", [])}
    available = {name.casefold(): name for name in module_list}
    for component_id in inspection.installed:
        spec = COMPONENTS[component_id]
        for alias in COMPONENT_ALIASES.get(component_id, (spec.filename,)):
            if alias.casefold() in available:
                values.add(available[alias.casefold()])
                break
    return sorted(values)


def make_checkpoint_manager_ui():
    global ui_forge_preset, ui_checkpoint, ui_vae, ui_forge_unet_dtype

    if shared.opts.sd_model_checkpoint in [None, "None", "none", ""]:
        if len(sd_models.checkpoints_list) == 0:
            sd_models.list_models()
        if len(sd_models.checkpoints_list) > 0:
            shared.opts.set("sd_model_checkpoint", next(iter(sd_models.checkpoints_list.values())).name)

    missing_components = gr.State([])
    ui_forge_preset = gr.Dropdown(label="Тип модели", value=lambda: shared.opts.forge_preset, choices=PresetArch.choices(), elem_id="forge_ui_preset")

    ui_checkpoint = gr.Dropdown(label="Checkpoint", value=None, choices=None, elem_id="setting_sd_model_checkpoint", elem_classes=["model_selection"])

    ui_vae = gr.Dropdown(label="VAE / Text Encoder", value=None, choices=None, multiselect=True, elem_id="setting_sd_modules", elem_classes=["model_selection"])

    def refresh_model_list():
        ckpt_list, vae_list = refresh_models()
        return [gr.update(choices=ckpt_list), gr.update(choices=vae_list)]

    refresh_button = ui_common.ToolButton(value=ui_common.refresh_symbol, elem_id="forge_refresh_checkpoint", tooltip="Refresh")
    refresh_event = refresh_button.click(fn=refresh_model_list, outputs=[ui_checkpoint, ui_vae], queue=False)
    load_event = Context.root_block.load(fn=refresh_model_list, outputs=[ui_checkpoint, ui_vae], queue=False)

    ui_forge_unet_dtype = gr.Dropdown(label="Хранение diffusion-модели", value=lambda: shared.opts.forge_unet_storage_dtype, choices=list(forge_unet_storage_dtype_options.keys()), elem_id="forge_ui_dtype")
    component_status = gr.Markdown("Выбери checkpoint — Atlas определит, какие VAE и text encoder уже встроены.", elem_classes=["atlas-model-component-status"])
    request_components = gr.Button("Докачать нужные модели?", variant="secondary", visible=False)
    with gr.Group(visible=False, elem_classes=["atlas-component-confirmation"]) as component_confirmation:
        component_confirmation_text = gr.Markdown()
        with gr.Row():
            confirm_components = gr.Button("Скачать компоненты", variant="primary")
            cancel_components = gr.Button("Отмена", variant="secondary")

    def inspect_selection(ckpt_name, selected_modules, current_preset):
        checkpoint = sd_models.get_closet_checkpoint_match(ckpt_name)
        if checkpoint is None:
            return current_preset, gr.skip(), "Checkpoint не найден.", [], gr.update(visible=False), gr.update(visible=False)
        inspection = inspect_checkpoint(checkpoint.filename, list(module_list))
        preset = inspection.preset or current_preset
        selected = _component_module_values(inspection, preset) if inspection.recognized else (selected_modules or [])
        modules_change(selected, preset, save=False, refresh=False)
        checkpoint_change(ckpt_name, preset, save=True, refresh=True)
        return preset, gr.update(value=selected), inspection.message, list(inspection.missing), gr.update(visible=bool(inspection.missing)), gr.update(visible=False)

    ui_checkpoint.input(
        inspect_selection,
        inputs=[ui_checkpoint, ui_vae, ui_forge_preset],
        outputs=[ui_forge_preset, ui_vae, component_status, missing_components, request_components, component_confirmation],
        queue=False,
        show_progress=False,
    )
    ui_vae.input(modules_change, inputs=[ui_vae, ui_forge_preset], queue=False, show_progress=False)
    ui_forge_unet_dtype.input(dtype_change, inputs=[ui_forge_unet_dtype, ui_forge_preset], queue=False, show_progress=False)

    def refresh_inspection(ckpt_name, selected_modules):
        checkpoint = sd_models.get_closet_checkpoint_match(ckpt_name)
        if checkpoint is None:
            return "Checkpoint не найден.", [], gr.update(visible=False), gr.update(visible=False)
        inspection = inspect_checkpoint(checkpoint.filename, list(module_list))
        return inspection.message, list(inspection.missing), gr.update(visible=bool(inspection.missing)), gr.update(visible=False)

    inspection_outputs = [component_status, missing_components, request_components, component_confirmation]
    refresh_event.then(refresh_inspection, inputs=[ui_checkpoint, ui_vae], outputs=inspection_outputs, queue=False, show_progress=False)
    load_event.then(refresh_inspection, inputs=[ui_checkpoint, ui_vae], outputs=inspection_outputs, queue=False, show_progress=False)
    ui_vae.change(refresh_inspection, inputs=[ui_checkpoint, ui_vae], outputs=inspection_outputs, queue=False, show_progress=False)

    def confirmation(component_ids):
        specs = [COMPONENTS[item] for item in component_ids]
        if not specs:
            return "Компоненты не требуются.", gr.update(visible=False)
        rows = ["### Будут скачаны только VAE и text encoder", ""]
        for spec in specs:
            rows.append(
                f"- **{spec.label}** · `{spec.filename}` · {spec.size:,} байт · лицензия: **{spec.license}**  \n"
                f"  [Источник](https://huggingface.co/{spec.repository}/blob/{spec.revision}/{spec.repository_path}) · "
                f"`{spec.repository}@{spec.revision}` → `{component_destination(spec)}`"
            )
        rows.extend(["", f"**Всего: {sum(spec.size for spec in specs):,} байт.** Основной checkpoint скачиваться не будет."])
        return "\n".join(rows), gr.update(visible=True)

    request_components.click(
        confirmation,
        inputs=[missing_components],
        outputs=[component_confirmation_text, component_confirmation],
        queue=False,
        show_progress=False,
    )

    def install_components(component_ids, selected_modules, preset, progress=gr.Progress()):
        def update(downloaded, total, filename):
            progress(downloaded / max(1, total), desc=f"{filename}: {downloaded:,} из {total:,} байт")

        installed = component_downloader.download(component_ids, update)
        checkpoints, choices = refresh_models()
        values = sorted({*(selected_modules or []), *(path.name for path in installed)})
        modules_change(values, preset, save=True, refresh=True)
        return (
            gr.update(choices=choices, value=values),
            "Компоненты скачаны, проверены и выбраны. Перезапуск не требуется.",
            [],
            gr.update(visible=False),
            gr.update(visible=False),
        )

    confirm_components.click(
        install_components,
        inputs=[missing_components, ui_vae, ui_forge_preset],
        outputs=[ui_vae, component_status, missing_components, request_components, component_confirmation],
        show_progress=True,
    )
    cancel_components.click(
        lambda: (component_downloader.cancel() or gr.update(visible=False)),
        outputs=[component_confirmation],
        queue=False,
        show_progress=False,
    )


def make_checkpoint_manager_mirror_ui() -> dict[str, object]:
    """Create a second visible view backed by the same Forge model state."""
    missing = gr.State([])
    with gr.Row():
        preset = gr.Dropdown(label="Тип модели", value=lambda: shared.opts.forge_preset, choices=PresetArch.choices(), elem_id="atlas_txt2img_model_preset")
        checkpoint = gr.Dropdown(label="Checkpoint", value=None, choices=None, elem_id="atlas_txt2img_checkpoint", elem_classes=["model_selection"])
        modules = gr.Dropdown(label="VAE / Text Encoder", value=None, choices=None, multiselect=True, elem_id="atlas_txt2img_modules", elem_classes=["model_selection"])
        refresh = ui_common.ToolButton(value=ui_common.refresh_symbol, elem_id="atlas_txt2img_model_refresh", tooltip="Обновить")
        dtype = gr.Dropdown(label="Хранение diffusion-модели", value=lambda: shared.opts.forge_unet_storage_dtype, choices=list(forge_unet_storage_dtype_options), elem_id="atlas_txt2img_dtype")
    status = gr.Markdown("Выбери checkpoint — Atlas проверит его состав.", elem_classes=["atlas-model-component-status"])
    request = gr.Button("Докачать нужные модели?", variant="secondary", visible=False)
    with gr.Group(visible=False, elem_classes=["atlas-component-confirmation"]) as confirmation:
        confirmation_text = gr.Markdown()
        with gr.Row():
            confirm = gr.Button("Скачать компоненты", variant="primary")
            cancel = gr.Button("Отмена", variant="secondary")
    return {"preset": preset, "checkpoint": checkpoint, "modules": modules, "refresh": refresh, "dtype": dtype, "status": status, "missing": missing, "request": request, "confirmation": confirmation, "confirmation_text": confirmation_text, "confirm": confirm, "cancel": cancel}


def bind_checkpoint_manager_mirror(view: dict[str, object]) -> None:
    def refresh_view():
        checkpoints, modules = refresh_models()
        return gr.update(choices=checkpoints, value=shared.opts.sd_model_checkpoint), gr.update(choices=modules, value=[os.path.basename(item) for item in shared.opts.forge_additional_modules])

    refresh_event = view["refresh"].click(refresh_view, outputs=[view["checkpoint"], view["modules"]], queue=False, show_progress=False)
    load_event = Context.root_block.load(refresh_view, outputs=[view["checkpoint"], view["modules"]], queue=False, show_progress=False)

    def inspect_view(ckpt_name, selected_modules, preset):
        checkpoint_info = sd_models.get_closet_checkpoint_match(ckpt_name)
        if checkpoint_info is None:
            return preset, "Checkpoint не найден.", [], gr.update(visible=False), gr.update(visible=False)
        inspection = inspect_checkpoint(checkpoint_info.filename, list(module_list))
        detected = inspection.preset or preset
        return detected, inspection.message, list(inspection.missing), gr.update(visible=bool(inspection.missing)), gr.update(visible=False)

    inspect_outputs = [view["preset"], view["status"], view["missing"], view["request"], view["confirmation"]]
    passive_inspect_outputs = [view["status"], view["missing"], view["request"], view["confirmation"]]
    refresh_event.then(inspect_view, inputs=[view["checkpoint"], view["modules"], view["preset"]], outputs=inspect_outputs, queue=False, show_progress=False)
    load_event.then(inspect_view, inputs=[view["checkpoint"], view["modules"], view["preset"]], outputs=inspect_outputs, queue=False, show_progress=False)

    def passive_inspect(ckpt_name, selected_modules, preset):
        _detected, status, missing, request, confirmation = inspect_view(ckpt_name, selected_modules, preset)
        return status, missing, request, confirmation

    view["modules"].change(passive_inspect, inputs=[view["checkpoint"], view["modules"], view["preset"]], outputs=passive_inspect_outputs, queue=False, show_progress=False)

    def choose_checkpoint(ckpt_name, selected_modules, preset):
        detected, status, missing, request, confirmation = inspect_view(ckpt_name, selected_modules, preset)
        checkpoint_info = sd_models.get_closet_checkpoint_match(ckpt_name)
        inspection = inspect_checkpoint(checkpoint_info.filename, list(module_list)) if checkpoint_info is not None else None
        selected = _component_module_values(inspection, detected) if inspection and inspection.recognized else (selected_modules or [])
        modules_change(selected, detected, save=False, refresh=False)
        checkpoint_change(ckpt_name, detected, save=True, refresh=True)
        return ckpt_name, selected, detected, detected, selected, status, missing, request, confirmation

    view["checkpoint"].input(
        choose_checkpoint,
        inputs=[view["checkpoint"], view["modules"], view["preset"]],
        outputs=[ui_checkpoint, ui_vae, ui_forge_preset, view["preset"], view["modules"], view["status"], view["missing"], view["request"], view["confirmation"]],
        queue=False,
        show_progress=False,
    )
    view["preset"].input(lambda value: value, inputs=[view["preset"]], outputs=[ui_forge_preset], queue=False, show_progress=False)

    def choose_modules(values, preset, ckpt_name):
        modules_change(values or [], preset, save=True, refresh=True)
        _detected, status, missing, request, confirmation = inspect_view(ckpt_name, values, preset)
        return values, status, missing, request, confirmation

    view["modules"].input(
        choose_modules,
        inputs=[view["modules"], view["preset"], view["checkpoint"]],
        outputs=[ui_vae, view["status"], view["missing"], view["request"], view["confirmation"]],
        queue=False,
        show_progress=False,
    )
    def choose_dtype(value, preset):
        dtype_change(value, preset)
        return value

    view["dtype"].input(choose_dtype, inputs=[view["dtype"], view["preset"]], outputs=[ui_forge_unet_dtype], queue=False, show_progress=False)

    ui_forge_preset.change(lambda value: value, inputs=[ui_forge_preset], outputs=[view["preset"]], queue=False, show_progress=False)
    ui_checkpoint.change(lambda value: value, inputs=[ui_checkpoint], outputs=[view["checkpoint"]], queue=False, show_progress=False)
    ui_vae.change(lambda value: value, inputs=[ui_vae], outputs=[view["modules"]], queue=False, show_progress=False)
    ui_forge_unet_dtype.change(lambda value: value, inputs=[ui_forge_unet_dtype], outputs=[view["dtype"]], queue=False, show_progress=False)

    def confirmation_text(component_ids):
        specs = [COMPONENTS[item] for item in component_ids]
        rows = ["### Будут скачаны только VAE и text encoder", ""]
        for spec in specs:
            rows.append(f"- **{spec.label}** · `{spec.filename}` · {spec.size:,} байт · **{spec.license}**  \n  [Источник](https://huggingface.co/{spec.repository}/blob/{spec.revision}/{spec.repository_path}) → `{component_destination(spec)}`")
        rows.append(f"\n**Всего: {sum(spec.size for spec in specs):,} байт.** Checkpoint скачиваться не будет.")
        return "\n".join(rows), gr.update(visible=bool(specs))

    view["request"].click(confirmation_text, inputs=[view["missing"]], outputs=[view["confirmation_text"], view["confirmation"]], queue=False, show_progress=False)

    def install(component_ids, selected_modules, preset, progress=gr.Progress()):
        def update(downloaded, total, filename):
            progress(downloaded / max(1, total), desc=f"{filename}: {downloaded:,} из {total:,} байт")

        installed = component_downloader.download(component_ids, update)
        _checkpoints, choices = refresh_models()
        values = sorted({*(selected_modules or []), *(path.name for path in installed)})
        modules_change(values, preset, save=True, refresh=True)
        return gr.update(choices=choices, value=values), gr.update(choices=choices, value=values), "Компоненты скачаны, проверены и выбраны.", [], gr.update(visible=False), gr.update(visible=False)

    view["confirm"].click(
        install,
        inputs=[view["missing"], view["modules"], view["preset"]],
        outputs=[view["modules"], ui_vae, view["status"], view["missing"], view["request"], view["confirmation"]],
        show_progress=True,
    )
    view["cancel"].click(lambda: (component_downloader.cancel() or gr.update(visible=False)), outputs=[view["confirmation"]], queue=False, show_progress=False)


def find_files_with_extensions(base_path: os.PathLike, extensions: list[str]) -> dict[str, os.PathLike]:
    found_files = {}
    for root, _, files in os.walk(base_path, followlinks=True):
        for file in files:
            if any(file.endswith(ext) for ext in extensions):
                full_path = os.path.join(root, file)
                found_files[file] = full_path
    return found_files


def refresh_models() -> tuple[list[os.PathLike], list[os.PathLike]]:
    shared_items.refresh_checkpoints()
    ckpt_list = shared_items.list_checkpoint_tiles(shared.opts.sd_checkpoint_dropdown_use_short)

    file_extensions = ("ckpt", "pt", "pth", "bin", "safetensors", "sft", "gguf")

    module_list.clear()

    module_paths: set[os.PathLike] = {
        os.path.abspath(os.path.join(paths.models_path, "VAE")),
        os.path.abspath(os.path.join(paths.models_path, "text_encoder")),
        *shared.cmd_opts.vae_dirs,
        *shared.cmd_opts.text_encoder_dirs,
    }

    for vae_path in module_paths:
        vae_files = find_files_with_extensions(vae_path, file_extensions)
        module_list.update(vae_files)

    return sorted(ckpt_list), sorted(module_list.keys())


def refresh_model_loading_parameters(*, refresh: bool = True):
    if not refresh:
        return

    from modules.sd_models import model_data, select_checkpoint

    checkpoint_info = select_checkpoint()
    if checkpoint_info is None:
        logger.critical('You do not have any model... Please download models to "models/Stable-diffusion"')
        return

    unet_storage_dtype, lora_fp16 = forge_unet_storage_dtype_options.get(shared.opts.forge_unet_storage_dtype, (None, False))

    model_data.forge_loading_parameters = dict(checkpoint_info=checkpoint_info, additional_modules=shared.opts.forge_additional_modules, unet_storage_dtype=unet_storage_dtype)

    ckpt: str = checkpoint_info.filename
    modules: list[str] = [os.path.basename(x) for x in shared.opts.forge_additional_modules]
    dtype = str(unet_storage_dtype or [torch.float16, torch.bfloat16])

    logger.info("Model Selected:")
    print_json(data=dict(checkpoint=os.path.basename(ckpt), modules=modules, dtype=dtype))

    if ckpt.endswith(("gguf", "GGUF")) and not lora_fp16:
        logger.warning("GGUF requires fp16 LoRA ; overriding option")
        lora_fp16 = True

    dynamic_args.online_lora = lora_fp16
    logger.info(f"Patch LoRAs on-the-fly: {lora_fp16}")

    processing.need_global_unload = True


def checkpoint_change(ckpt_name: str, preset: str, save=True, refresh=True) -> bool:
    """`ckpt_name` accepts valid aliases; returns `True` if checkpoint changed"""
    new_ckpt_info = sd_models.get_closet_checkpoint_match(ckpt_name)
    current_ckpt_info = sd_models.get_closet_checkpoint_match(getattr(shared.opts, "sd_model_checkpoint", ""))
    if new_ckpt_info == current_ckpt_info:
        return False

    shared.opts.set("sd_model_checkpoint", ckpt_name)
    if preset is not None:
        shared.opts.set(f"forge_checkpoint_{preset}", ckpt_name)

    if save:
        shared.opts.save(shared.config_filename)
    refresh_model_loading_parameters(refresh=refresh)
    return True


def modules_change(module_values: list, preset: str, save=True, refresh=True) -> bool:
    """`module_values` accepts file paths or just the module names; returns `True` if modules changed"""
    modules = []
    for v in module_values:
        module_name = os.path.basename(v)  # If the input is a filepath, extract the filename
        if module_name in module_list:
            modules.append(module_list[module_name])
    modules.sort()

    # skip further processing if value unchanged
    if modules == getattr(shared.opts, "forge_additional_modules", []):
        return False

    shared.opts.set("forge_additional_modules", modules)
    if preset is not None:
        shared.opts.set(f"forge_additional_modules_{preset}", modules)

    if save:
        shared.opts.save(shared.config_filename)
    refresh_model_loading_parameters(refresh=refresh)
    return True


def dtype_change(dtype: str, preset: str, save=True, refresh=True) -> bool:
    shared.opts.set("forge_unet_storage_dtype", dtype)
    if preset is not None:
        shared.opts.set(f"forge_unet_storage_dtype_{preset}", dtype)

    if save:
        shared.opts.save(shared.config_filename)
    refresh_model_loading_parameters(refresh=refresh)
    return True


def get_a1111_ui_component(tab: str, label: str) -> gr.components.Component:
    fields = infotext_utils.paste_fields[tab]["fields"]
    for f in fields:
        if f.label == label or f.api == label:
            return f.component


def forge_main_entry():
    ui_txt2img_steps = get_a1111_ui_component("txt2img", "Steps")
    ui_txt2img_hr_steps = get_a1111_ui_component("txt2img", "Hires steps")
    ui_img2img_steps = get_a1111_ui_component("img2img", "Steps")

    ui_txt2img_sampler = get_a1111_ui_component("txt2img", "sampler_name")
    ui_img2img_sampler = get_a1111_ui_component("img2img", "sampler_name")
    ui_txt2img_scheduler = get_a1111_ui_component("txt2img", "scheduler")
    ui_img2img_scheduler = get_a1111_ui_component("img2img", "scheduler")

    ui_txt2img_width = get_a1111_ui_component("txt2img", "Size-1")
    ui_img2img_width = get_a1111_ui_component("img2img", "Size-1")
    ui_txt2img_height = get_a1111_ui_component("txt2img", "Size-2")
    ui_img2img_height = get_a1111_ui_component("img2img", "Size-2")

    ui_txt2img_cfg = get_a1111_ui_component("txt2img", "CFG scale")
    ui_txt2img_hr_cfg = get_a1111_ui_component("txt2img", "Hires CFG Scale")
    ui_img2img_cfg = get_a1111_ui_component("img2img", "CFG scale")

    ui_txt2img_distilled_cfg = get_a1111_ui_component("txt2img", "Distilled CFG Scale")
    ui_txt2img_hr_distilled_cfg = get_a1111_ui_component("txt2img", "Hires Distilled CFG Scale")
    ui_img2img_distilled_cfg = get_a1111_ui_component("img2img", "Distilled CFG Scale")

    ui_txt2img_batch_size = get_a1111_ui_component("txt2img", "Batch size")
    ui_img2img_batch_size = get_a1111_ui_component("img2img", "Batch size")

    output_targets = [
        ui_checkpoint,
        ui_vae,
        ui_forge_unet_dtype,
        ui_txt2img_steps,
        ui_txt2img_hr_steps,
        ui_img2img_steps,
        ui_txt2img_sampler,
        ui_img2img_sampler,
        ui_txt2img_scheduler,
        ui_img2img_scheduler,
        ui_txt2img_width,
        ui_img2img_width,
        ui_txt2img_height,
        ui_img2img_height,
        ui_txt2img_cfg,
        ui_txt2img_hr_cfg,
        ui_img2img_cfg,
        ui_txt2img_distilled_cfg,
        ui_txt2img_hr_distilled_cfg,
        ui_img2img_distilled_cfg,
        ui_txt2img_batch_size,
        ui_img2img_batch_size,
    ]

    ui_forge_preset.change(on_preset_change, inputs=[ui_forge_preset], outputs=output_targets, queue=False, show_progress=False).success(
        fn=_load_presets,
        inputs=[ui_checkpoint, ui_vae, ui_forge_unet_dtype, ui_forge_preset],
        queue=False,
        show_progress=False,
    ).then(js="clickLoraRefresh", fn=None, queue=False, show_progress=False)
    Context.root_block.load(on_preset_change, inputs=[ui_forge_preset], outputs=output_targets, queue=False, show_progress=False)

    refresh_model_loading_parameters()


def _load_presets(ui_checkpoint: str, ui_vae: list[str], ui_forge_unet_dtype: str, ui_forge_preset: str):
    dtype_change(ui_forge_unet_dtype, ui_forge_preset, save=False, refresh=False)
    modules_change(ui_vae, ui_forge_preset, save=False, refresh=False)
    checkpoint_change(ui_checkpoint, ui_forge_preset, save=True, refresh=True)


def on_preset_change(preset: str):
    assert preset is not None
    shared.opts.set("forge_preset", preset)
    shared.opts.save(shared.config_filename)

    if use_shift(preset):
        d_args = {"visible": getattr(shared.opts, f"{preset}_show_shift", True), "label": "Shift"}
    elif use_distill(preset):
        d_args = {"visible": True, "label": "Distilled CFG Scale"}
    else:
        d_args = {"visible": False}

    if (fps := is_video(preset)) > 1:
        batch_args_t2i = {"minimum": 1, "maximum": fps * 15 + 1, "step": fps, "label": "Frames", "value": getattr(shared.opts, f"{preset}_t2i_batch_size", 1)}
    else:
        batch_args_t2i = {"minimum": 1, "maximum": 8, "step": 1, "label": "Batch Size", "value": getattr(shared.opts, f"{preset}_t2i_batch_size", 1)}

    batch_args_i2i = batch_args_t2i.copy()
    batch_args_i2i["value"] = getattr(shared.opts, f"{preset}_i2i_batch_size", 1)

    return [
        # ui_checkpoint, ui_vae, ui_forge_unet_dtype
        gr.update(value=getattr(shared.opts, f"forge_checkpoint_{preset}", shared.opts.sd_model_checkpoint)),
        gr.update(value=[os.path.basename(m) for m in getattr(shared.opts, f"forge_additional_modules_{preset}", [])]),
        gr.update(value=getattr(shared.opts, f"forge_unet_storage_dtype_{preset}", "Automatic")),
        # ui_txt2img_steps, ui_txt2img_hr_steps, ui_img2img_steps
        gr.update(value=v) if (v := getattr(shared.opts, f"{preset}_t2i_step", 20)) > 0 else gr.skip(),
        gr.update(value=v) if (v := getattr(shared.opts, f"{preset}_t2i_hr_step", 20)) > 0 else gr.skip(),
        gr.update(value=v) if (v := getattr(shared.opts, f"{preset}_i2i_step", 20)) > 0 else gr.skip(),
        # ui_txt2img_sampler, ui_img2img_sampler, ui_txt2img_scheduler, ui_img2img_scheduler
        gr.update(value=getattr(shared.opts, f"{preset}_t2i_sampler", "Euler")),
        gr.update(value=getattr(shared.opts, f"{preset}_i2i_sampler", "Euler")),
        gr.update(value=getattr(shared.opts, f"{preset}_t2i_scheduler", "Simple")),
        gr.update(value=getattr(shared.opts, f"{preset}_i2i_scheduler", "Simple")),
        # ui_txt2img_width, ui_img2img_width, ui_txt2img_height, ui_img2img_height
        gr.update(value=v) if (v := getattr(shared.opts, f"{preset}_t2i_width", 1024)) > 0 else gr.skip(),
        gr.update(value=v) if (v := getattr(shared.opts, f"{preset}_i2i_width", 1024)) > 0 else gr.skip(),
        gr.update(value=v) if (v := getattr(shared.opts, f"{preset}_t2i_height", 1024)) > 0 else gr.skip(),
        gr.update(value=v) if (v := getattr(shared.opts, f"{preset}_i2i_height", 1024)) > 0 else gr.skip(),
        # ui_txt2img_cfg, ui_txt2img_hr_cfg, ui_img2img_cfg
        gr.update(value=v) if (v := getattr(shared.opts, f"{preset}_t2i_cfg", 1.0)) > 0 else gr.skip(),
        gr.update(value=v) if (v := getattr(shared.opts, f"{preset}_t2i_hr_cfg", 1.0)) > 0 else gr.skip(),
        gr.update(value=v) if (v := getattr(shared.opts, f"{preset}_i2i_cfg", 1.0)) > 0 else gr.skip(),
        # ui_txt2img_distilled_cfg, ui_img2img_distilled_cfg, ui_txt2img_hr_distilled_cfg
        gr.update(value=getattr(shared.opts, f"{preset}_t2i_dcfg", 3.0), **d_args),
        gr.update(value=getattr(shared.opts, f"{preset}_t2i_hr_dcfg", 3.0), **d_args),
        gr.update(value=getattr(shared.opts, f"{preset}_i2i_dcfg", 3.0), **d_args),
        # ui_txt2img_batch_size, ui_img2img_batch_size
        gr.update(**batch_args_t2i),
        gr.update(**batch_args_i2i),
    ]
