from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import gradio as gr

from modules import sd_samplers, sd_schedulers, shared
from modules.call_queue import queue_lock, wrap_gradio_gpu_call
from modules_forge.autoprompt.download import FLORENCE_LICENSE, FLORENCE_REPO, FLORENCE_REVISION, FLORENCE_TOTAL_BYTES, FlorenceDownloader
from modules_forge.autoprompt.model import florence_is_installed, florence_model_path, service as florence_service
from modules_forge.large_upscale.contracts import LargeUpscaleJobSpec, SourceAsset
from modules_forge.large_upscale.preflight import build_preflight
from modules_forge.large_upscale.runner import forge_tile_processor, run_large_upscale
from modules_forge.large_upscale.source import choose_source_image, describe_source, format_file_size, inspect_source
from modules_forge.presets import use_distill, use_shift


florence_downloader = FlorenceDownloader()


def _asset_json(asset: SourceAsset) -> str:
    return json.dumps(asset.__dict__, ensure_ascii=False)


def _asset_from_json(value: str) -> SourceAsset:
    if not value:
        raise ValueError("Сначала выбери исходное изображение.")
    return SourceAsset.from_dict(json.loads(value))


def _select_source(current_path: str = ""):
    selected = choose_source_image(current_path)
    if not selected:
        return gr.skip(), gr.skip(), gr.skip(), "Изображение не выбрано."
    asset = inspect_source(
        selected,
        proxy_max_side=int(shared.opts.atlas_proxy_max_side),
        proxy_max_payload_bytes=int(shared.opts.atlas_proxy_max_payload_mb) * 1024 * 1024,
    )
    return _asset_json(asset), asset.path, asset.proxy_path, describe_source(asset)


def _choose_output_folder(current_path: str = "") -> str:
    from tkinter import Tk, filedialog

    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(
            initialdir=current_path if current_path and Path(current_path).is_dir() else shared.opts.outdir_img2img_samples,
            title="Выбери папку для результата",
        )
    finally:
        root.destroy()
    return selected or current_path


def _open_folder(path: str) -> str:
    target = Path(path)
    folder = target if target.is_dir() else target.parent
    if not folder.is_dir():
        return "Папка пока не существует."
    if os.name == "nt":
        os.startfile(folder)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(folder)])
    else:
        subprocess.Popen(["xdg-open", str(folder)])
    return f"Открыта папка `{folder}`."


def _target_dimensions(asset: SourceAsset, scale_factor: float) -> tuple[int, int]:
    scale = max(1.0, float(scale_factor))
    return max(1, round(asset.width * scale)), max(1, round(asset.height * scale))


def _tile_dimensions(mode: str, width: int, height: int) -> tuple[int, int]:
    if mode == "Автоматически":
        try:
            import torch

            vram = torch.cuda.get_device_properties(0).total_memory if torch.cuda.is_available() else 0
        except Exception:
            vram = 0
        preset = shared.opts.forge_preset
        if preset == "sd":
            size = 1280 if vram >= 20 * 1024**3 else 1024 if vram >= 10 * 1024**3 else 768
        else:
            size = 1024 if vram >= 20 * 1024**3 else 768 if vram >= 10 * 1024**3 else 512
        return size, size
    return max(256, int(width)), max(256, int(height))


SPEC_ARGUMENTS = (
    "source_json",
    "size_mode",
    "scale_factor",
    "profile",
    "denoising",
    "prompt",
    "analysis_profile",
    "negative_prompt",
    "sampler",
    "scheduler",
    "steps",
    "cfg",
    "distilled_cfg",
    "seed",
    "tile_mode",
    "tile_width",
    "tile_height",
    "overlap",
    "seam_blending",
    "upscaler",
    "vae_tiling",
    "output_folder",
    "output_format",
    "quality",
    "keep_metadata",
    "keep_icc",
    "keep_alpha",
    "resume",
    "cleanup",
)


def _make_spec(*values) -> LargeUpscaleJobSpec:
    args = dict(zip(SPEC_ARGUMENTS, values))
    asset = _asset_from_json(args["source_json"])
    target_width, target_height = _target_dimensions(asset, args["scale_factor"])
    tile_width, tile_height = _tile_dimensions(args["tile_mode"], args["tile_width"], args["tile_height"])
    overlap = max(32, min(tile_width, tile_height) // 8) if args["tile_mode"] == "Автоматически" else int(args["overlap"])
    output_format = str(args["output_format"]).lower()
    extension = "jpg" if output_format == "jpeg" else output_format
    output_root = Path(args["output_folder"] or shared.opts.atlas_upscale_output_dir or shared.opts.outdir_img2img_samples).expanduser().resolve()
    signature_data = {
        **{key: value for key, value in args.items() if key not in {"source_json", "output_folder"}},
        "fingerprint": asset.fingerprint,
        "target": [target_width, target_height],
        "checkpoint": shared.opts.sd_model_checkpoint,
        "modules": shared.opts.forge_additional_modules,
    }
    signature = hashlib.sha256(json.dumps(signature_data, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    resolved_seed = int(asset.fingerprint[:8], 16) if int(args["seed"]) == -1 else int(args["seed"])
    output_path = output_root / f"{Path(asset.path).stem}-atlas-{signature}.{extension}"
    temp_root = shared.opts.atlas_upscale_temp_dir or ""
    return LargeUpscaleJobSpec(
        job_id=f"upscale-{asset.fingerprint[:12]}-{signature}",
        source=asset,
        target_width=target_width,
        target_height=target_height,
        prompt=args["prompt"],
        negative_prompt=args["negative_prompt"],
        analysis_profile=args["analysis_profile"],
        profile=args["profile"],
        denoising_strength=float(args["denoising"]),
        sampler_name=args["sampler"],
        scheduler=args["scheduler"],
        steps=int(args["steps"]),
        cfg_scale=float(args["cfg"]),
        distilled_cfg_scale=float(args["distilled_cfg"]),
        seed=resolved_seed,
        tile_width=tile_width,
        tile_height=tile_height,
        overlap=overlap,
        seam_blending=args["seam_blending"],
        upscaler_name=args["upscaler"],
        vae_tiling=bool(args["vae_tiling"]),
        output_path=str(output_path),
        output_format=output_format,
        jpeg_quality=int(args["quality"]),
        webp_lossless=False,
        keep_metadata=bool(args["keep_metadata"]),
        keep_icc=bool(args["keep_icc"]),
        keep_alpha=bool(args["keep_alpha"]),
        resume_enabled=bool(args["resume"]),
        cleanup_after_success=bool(args["cleanup"]),
        keep_temp_on_error=bool(shared.opts.atlas_keep_temp_on_error),
        temp_root=temp_root,
        assembly_block_size=int(shared.opts.atlas_assembly_block_size),
        proxy_max_side=int(shared.opts.atlas_proxy_max_side),
        proxy_max_payload_bytes=int(shared.opts.atlas_proxy_max_payload_mb) * 1024 * 1024,
        checkpoint=shared.opts.sd_model_checkpoint,
        additional_modules=tuple(shared.opts.forge_additional_modules),
        model_preset=shared.opts.forge_preset,
    )


def _preflight(*values):
    try:
        spec = _make_spec(*values)
    except (ValueError, FileNotFoundError) as error:
        return f"### Нужен исходник\n\n{error}", gr.update(interactive=False)
    report = build_preflight(spec)
    details = (
        f"\n\nТайлы: **{spec.tile_width} × {spec.tile_height}**, overlap **{spec.overlap} px**, "
        f"сборка блоками **{spec.assembly_block_size} px**, seed **{spec.seed}**."
    )
    return report.to_markdown(spec.target_width, spec.target_height, spec.output_format) + details, gr.update(interactive=report.can_start)


def _run_upscale(*values, progress=gr.Progress()):
    spec = _make_spec(*values)
    report = build_preflight(spec)
    if not report.can_start:
        raise ValueError(" ".join(report.errors))

    def update(value: float, message: str):
        progress(value, desc=message)
        shared.state.textinfo = message
        shared.state.job_count = max(1, len(report.tiles))
        shared.state.job_no = min(len(report.tiles), round(value * len(report.tiles)))

    result = run_large_upscale(
        spec,
        forge_tile_processor,
        progress=update,
        cancelled=lambda: shared.state.interrupted or shared.state.stopping_generation,
    )
    info = f"**{result.width} × {result.height}** · {result.format} · {format_file_size(result.file_size)}\n\n`{result.path}`"
    return (
        result.proxy_path,
        info,
        result.path,
        result.path,
        gr.update(interactive=True),
        gr.update(interactive=True),
        "### Готово\n\nПолный файл сохранён на диске; браузер показывает только proxy.",
    )


def _install_florence_inline(progress=gr.Progress()):
    destination = florence_model_path(shared.opts.atlas_autoprompt_model_dir)

    def update(downloaded: int, total: int, filename: str):
        progress(downloaded / max(1, total), desc=f"{filename}: {format_file_size(downloaded)} из {format_file_size(total)}")

    florence_downloader.download(destination, update)
    return (
        "Модель Autoprompt установлена и будет загружена только при анализе изображения.",
        gr.update(visible=False),
        gr.update(visible=False),
        gr.update(visible=True, interactive=True),
    )


def _analyse_autoprompt(source_json: str):
    asset = _asset_from_json(source_json)
    use_gpu = shared.opts.atlas_autoprompt_device == "GPU"
    if use_gpu:
        with queue_lock:
            prompt, raw, profile = florence_service.analyse(
                asset.proxy_path,
                configured_path=shared.opts.atlas_autoprompt_model_dir,
                use_gpu=True,
                max_prompt_length=int(shared.opts.atlas_autoprompt_max_length),
                retention_minutes=int(shared.opts.atlas_autoprompt_retention_minutes),
            )
    else:
        prompt, raw, profile = florence_service.analyse(
            asset.proxy_path,
            configured_path=shared.opts.atlas_autoprompt_model_dir,
            use_gpu=False,
            max_prompt_length=int(shared.opts.atlas_autoprompt_max_length),
            retention_minutes=int(shared.opts.atlas_autoprompt_retention_minutes),
        )
    return prompt, raw, profile, "Промпт готов. Он описывает общую визуальную систему, а не локальные предметы."


def create_upscale_workspace() -> tuple[gr.Blocks, dict[str, object]]:
    sampler_choices = sd_samplers.visible_sampler_names()
    scheduler_choices = [item.label for item in sd_schedulers.schedulers]
    upscaler_choices = [item.name for item in shared.sd_upscalers]
    default_output = shared.opts.atlas_upscale_output_dir or shared.opts.outdir_img2img_samples
    preset = shared.opts.forge_preset
    default_sampler = getattr(shared.opts, f"{preset}_i2i_sampler", sampler_choices[0] if sampler_choices else None)
    default_scheduler = getattr(shared.opts, f"{preset}_i2i_scheduler", scheduler_choices[0] if scheduler_choices else None)
    default_steps = getattr(shared.opts, f"{preset}_i2i_step", 24) or 24
    default_cfg = getattr(shared.opts, f"{preset}_i2i_cfg", 6.0)
    default_distilled = getattr(shared.opts, f"{preset}_i2i_dcfg", 3.0)
    automatic_tile_width, automatic_tile_height = _tile_dimensions("Автоматически", 1024, 1024)
    automatic_overlap = max(32, min(automatic_tile_width, automatic_tile_height) // 8)
    autoprompt_installed = florence_is_installed(shared.opts.atlas_autoprompt_model_dir)
    with gr.Blocks(analytics_enabled=False) as interface:
        source_state = gr.State("")
        result_path_state = gr.State("")
        autoprompt_profile = gr.State("")
        raw_autoprompt = gr.State("")
        with gr.Row(elem_classes=["atlas-workspace"]):
            with gr.Column(elem_classes=["atlas-card", "atlas-source-result"]):
                gr.Markdown("## Изображение и результат")
                choose = gr.Button("Выбрать изображение", variant="primary")
                source_path = gr.Textbox(label="Настоящий исходный файл", interactive=False)
                source_proxy = gr.Image(label="Исходник · proxy", interactive=False, type="filepath", height=420)
                source_info = gr.Markdown("Выбери изображение для улучшения.", elem_classes=["atlas-status-slot"])
                with gr.Row():
                    replace_source = gr.Button("Заменить", variant="secondary")
                    open_source = gr.Button("Открыть папку", variant="secondary")
                result_proxy = gr.Image(label="Результат · proxy", interactive=False, type="filepath", height=420)
                result_info = gr.Markdown("Здесь появится bounded proxy результата.", elem_classes=["atlas-status-slot"])
                with gr.Row():
                    open_result = gr.Button("Открыть папку", variant="secondary")
                    download = gr.DownloadButton("Скачать полный файл", variant="primary")
                with gr.Row():
                    less_detail = gr.Button("Повторить с меньшей детализацией", variant="secondary", interactive=False)
                    more_detail = gr.Button("Повторить с большей детализацией", variant="secondary", interactive=False)

            with gr.Column(elem_classes=["atlas-controls"]):
                with gr.Group(elem_classes=["atlas-card"]):
                    gr.Markdown("### 1. Размер результата")
                    size_mode = gr.Radio(["2×", "4×", "Вручную"], value="2×", label="Режим")
                    scale_factor = gr.Slider(1, 8, value=2, step=0.05, label="Масштаб, ×")

                with gr.Group(elem_classes=["atlas-card"]):
                    gr.Markdown("### 2. Характер улучшения")
                    profile = gr.Radio(["Сохранить оригинал", "Добавить детали", "Сильнее перерисовать", "Вручную"], value="Добавить детали", label="Профиль")
                    denoising = gr.Slider(0, 1, value=0.35, step=0.01, label="Сила перерисовки")

                with gr.Group(elem_classes=["atlas-card", "atlas-prompt-card"]):
                    gr.Markdown("### 3. Промпт")
                    prompt = gr.Textbox(label="Prompt", lines=5, max_lines=16, elem_classes=["atlas-autogrow"])
                    negative_prompt = gr.Textbox(label="Negative Prompt", lines=3, max_lines=12, elem_classes=["atlas-autogrow"])
                    create_autoprompt = gr.Button("Создать автопромпт", variant="secondary", visible=autoprompt_installed, elem_classes=["atlas-prompt-action"])
                    install_autoprompt_info = gr.Markdown(
                        f"Для автопромпта нужна **[{FLORENCE_REPO}](https://huggingface.co/{FLORENCE_REPO}/tree/{FLORENCE_REVISION})** · "
                        f"revision `{FLORENCE_REVISION}` · лицензия **{FLORENCE_LICENSE}** · "
                        f"загрузка **{format_file_size(FLORENCE_TOTAL_BYTES)}** в `{florence_model_path(shared.opts.atlas_autoprompt_model_dir)}`.",
                        visible=not autoprompt_installed,
                    )
                    install_autoprompt = gr.Button("Скачать модель автопромпта", variant="secondary", visible=not autoprompt_installed, elem_classes=["atlas-prompt-action"])
                    prompt_hint = gr.Markdown("Не перечисляй точные объекты и надписи: они могут повториться между тайлами.", elem_classes=["atlas-status-slot"])

                with gr.Group(elem_classes=["atlas-card"]):
                    gr.Markdown("### 4. Качество генерации")
                    with gr.Row():
                        sampler = gr.Dropdown(sampler_choices, value=default_sampler, label="Sampler")
                        scheduler = gr.Dropdown(scheduler_choices, value=default_scheduler, label="Scheduler")
                    with gr.Row():
                        steps = gr.Slider(1, 150, value=default_steps, step=1, label="Steps")
                        cfg = gr.Slider(1, 24, value=default_cfg, step=0.5, label="CFG")
                        distilled_cfg = gr.Slider(
                            0,
                            24,
                            value=default_distilled,
                            step=0.5,
                            label="Shift" if use_shift(preset) else "Distilled CFG",
                            visible=use_distill(preset) or use_shift(preset),
                        )
                    seed = gr.Number(label="Seed", value=-1, precision=0)
                    gr.Number(label="Batch size · ограничен для стабильной памяти", value=1, precision=0, interactive=False)

                with gr.Group(elem_classes=["atlas-card"]):
                    gr.Markdown("### 5. Upscale и тайлы")
                    upscaler = gr.Dropdown(upscaler_choices, value="Lanczos" if "Lanczos" in upscaler_choices else (upscaler_choices[0] if upscaler_choices else None), label="Пиксельный upscaler")
                    tile_mode = gr.Radio(["Автоматически", "Вручную"], value="Автоматически", label="Конфигурация тайлов")
                    with gr.Row():
                        tile_width = gr.Number(label="Ширина тайла", value=automatic_tile_width, precision=0, minimum=256, interactive=False)
                        tile_height = gr.Number(label="Высота тайла", value=automatic_tile_height, precision=0, minimum=256, interactive=False)
                        overlap = gr.Number(label="Overlap", value=automatic_overlap, precision=0, minimum=0, interactive=False)
                    seam_blending = gr.Dropdown(["cosine", "feather"], value="cosine", label="Смешивание границ")
                    vae_tiling = gr.Checkbox(label="Обрабатывать VAE ограниченно, по одному тайлу", value=True, interactive=False)
                    gr.Markdown("Сторонние img2img scripts здесь не запускаются без проверки tile-safety. Они полностью доступны в классическом img2img.")

                with gr.Group(elem_classes=["atlas-card"]):
                    gr.Markdown("### 6. Сохранение")
                    with gr.Row():
                        output_folder = gr.Textbox(label="Папка результата", value=default_output)
                        choose_output = gr.Button("Выбрать", variant="secondary", scale=0)
                    with gr.Row():
                        output_format = gr.Dropdown(["png", "jpg", "webp"], value=shared.opts.samples_format if shared.opts.samples_format in {"png", "jpg", "webp"} else "png", label="Формат")
                        quality = gr.Slider(1, 100, value=shared.opts.jpeg_quality, step=1, label="Качество JPEG/WebP")
                    keep_metadata = gr.Checkbox(label="Сохранить metadata / infotext", value=True)
                    keep_icc = gr.Checkbox(label="Сохранить ICC, если формат поддерживает", value=True)
                    keep_alpha = gr.Checkbox(label="Сохранить alpha, если формат поддерживает", value=True)
                    resume = gr.Checkbox(label="Разрешить возобновление", value=True)
                    cleanup = gr.Checkbox(label="Удалить временные тайлы после успеха", value=True)

                with gr.Group(elem_classes=["atlas-preflight"]):
                    preflight = gr.Markdown("Выбери исходник — Atlas рассчитает тайлы, место на диске и реальные ограничения.", elem_classes=["atlas-status-slot"])
                    with gr.Row():
                        check = gr.Button("Проверить перед запуском", variant="secondary")
                        start = gr.Button("Начать улучшение", variant="primary", interactive=False)
                        cancel = gr.Button("Отменить", variant="stop")

        spec_inputs = [
            source_state,
            size_mode,
            scale_factor,
            profile,
            denoising,
            prompt,
            autoprompt_profile,
            negative_prompt,
            sampler,
            scheduler,
            steps,
            cfg,
            distilled_cfg,
            seed,
            tile_mode,
            tile_width,
            tile_height,
            overlap,
            seam_blending,
            upscaler,
            vae_tiling,
            output_folder,
            output_format,
            quality,
            keep_metadata,
            keep_icc,
            keep_alpha,
            resume,
            cleanup,
        ]
        choose_event = choose.click(_select_source, inputs=[source_path], outputs=[source_state, source_path, source_proxy, source_info], queue=False, show_progress=False)
        replace_event = replace_source.click(_select_source, inputs=[source_path], outputs=[source_state, source_path, source_proxy, source_info], queue=False, show_progress=False)
        choose_event.then(_preflight, inputs=spec_inputs, outputs=[preflight, start], queue=False, show_progress=False)
        replace_event.then(_preflight, inputs=spec_inputs, outputs=[preflight, start], queue=False, show_progress=False)
        open_source.click(_open_folder, inputs=[source_path], outputs=[source_info], queue=False)
        choose_output.click(_choose_output_folder, inputs=[output_folder], outputs=[output_folder], queue=False)
        check.click(_preflight, inputs=spec_inputs, outputs=[preflight, start], queue=False, show_progress=False)
        for component in spec_inputs[1:]:
            component.change(_preflight, inputs=spec_inputs, outputs=[preflight, start], queue=False, show_progress=False)
        create_autoprompt.click(
            _analyse_autoprompt,
            inputs=[source_state],
            outputs=[prompt, raw_autoprompt, autoprompt_profile, prompt_hint],
        )
        install_autoprompt.click(
            _install_florence_inline,
            outputs=[prompt_hint, install_autoprompt_info, install_autoprompt, create_autoprompt],
            show_progress=True,
        )
        run_outputs = [result_proxy, result_info, download, result_path_state, less_detail, more_detail, preflight]
        start.click(
            wrap_gradio_gpu_call(_run_upscale, extra_outputs=[None, "", None, "", gr.skip(), gr.skip()]),
            inputs=spec_inputs,
            outputs=run_outputs,
            show_progress=False,
        )
        cancel.click(fn=lambda: shared.state.interrupt() or "Отмена запрошена. Уже готовые тайлы будут сохранены для продолжения.", outputs=[preflight], queue=False)
        open_result.click(_open_folder, inputs=[result_path_state], outputs=[result_info], queue=False)
        profile.change(
            lambda value: {"Сохранить оригинал": 0.2, "Добавить детали": 0.35, "Сильнее перерисовать": 0.55}.get(value, gr.skip()),
            inputs=[profile],
            outputs=[denoising],
            queue=False,
        )
        denoising.input(lambda _value: "Вручную", inputs=[denoising], outputs=[profile], queue=False, show_progress=False)
        size_mode.change(
            lambda mode, current: 2 if mode == "2×" else 4 if mode == "4×" else current,
            inputs=[size_mode, scale_factor],
            outputs=[scale_factor],
            queue=False,
            show_progress=False,
        )
        scale_factor.input(lambda _value: "Вручную", inputs=[scale_factor], outputs=[size_mode], queue=False, show_progress=False)
        tile_mode.change(
            lambda mode: (
                gr.update(interactive=mode == "Вручную", value=_tile_dimensions(mode, automatic_tile_width, automatic_tile_height)[0]),
                gr.update(interactive=mode == "Вручную", value=_tile_dimensions(mode, automatic_tile_width, automatic_tile_height)[1]),
                gr.update(interactive=mode == "Вручную", value=automatic_overlap),
            ),
            inputs=[tile_mode],
            outputs=[tile_width, tile_height, overlap],
            queue=False,
            show_progress=False,
        )
        less_detail.click(lambda value: max(0, value - 0.1), inputs=[denoising], outputs=[denoising], queue=False).then(
            wrap_gradio_gpu_call(_run_upscale, extra_outputs=[None, "", None, "", gr.skip(), gr.skip()]),
            inputs=spec_inputs,
            outputs=run_outputs,
            show_progress=False,
        )
        more_detail.click(lambda value: min(1, value + 0.1), inputs=[denoising], outputs=[denoising], queue=False).then(
            wrap_gradio_gpu_call(_run_upscale, extra_outputs=[None, "", None, "", gr.skip(), gr.skip()]),
            inputs=spec_inputs,
            outputs=run_outputs,
            show_progress=False,
        )

    return interface, {
        "source_state": source_state,
        "source_path": source_path,
        "proxy": source_proxy,
        "source_info": source_info,
        "prompt": prompt,
        "profile": autoprompt_profile,
        "prompt_hint": prompt_hint,
        "sampler": sampler,
        "scheduler": scheduler,
        "steps": steps,
        "cfg": cfg,
        "distilled_cfg": distilled_cfg,
        "spec_inputs": spec_inputs,
        "preflight": preflight,
        "start": start,
    }


def bind_global_model_state(upscale: dict[str, object], checkpoint, modules, preset_component) -> None:
    checkpoint.change(_preflight, inputs=upscale["spec_inputs"], outputs=[upscale["preflight"], upscale["start"]], queue=False, show_progress=False)
    modules.change(_preflight, inputs=upscale["spec_inputs"], outputs=[upscale["preflight"], upscale["start"]], queue=False, show_progress=False)

    def preset_values(preset):
        distilled_visible = use_distill(preset) or use_shift(preset)
        distilled_label = "Shift" if use_shift(preset) else "Distilled CFG"
        return (
            getattr(shared.opts, f"{preset}_i2i_sampler", gr.skip()),
            getattr(shared.opts, f"{preset}_i2i_scheduler", gr.skip()),
            getattr(shared.opts, f"{preset}_i2i_step", gr.skip()),
            getattr(shared.opts, f"{preset}_i2i_cfg", gr.skip()),
            gr.update(value=getattr(shared.opts, f"{preset}_i2i_dcfg", 3.0), visible=distilled_visible, label=distilled_label),
        )

    preset_component.change(
        preset_values,
        inputs=[preset_component],
        outputs=[upscale["sampler"], upscale["scheduler"], upscale["steps"], upscale["cfg"], upscale["distilled_cfg"]],
        queue=False,
        show_progress=False,
    )
    preset_component.change(_preflight, inputs=upscale["spec_inputs"], outputs=[upscale["preflight"], upscale["start"]], queue=False, show_progress=False)
