def register(options_templates, options_section, OptionInfo):
    from pathlib import Path

    import gradio as gr

    from modules import paths
    from modules.ui_components import FormColorPicker

    options_templates.update(
        options_section(
            (None, "Forge Hidden Options"),
            {
                "VERSION_UID": OptionInfo(None, "internal version for breaking-changes"),
                "forge_preset": OptionInfo("sd"),
                "forge_additional_modules": OptionInfo([]),
                "forge_unet_storage_dtype": OptionInfo("Automatic"),
                "atlas_autoprompt_onboarding_dismissed": OptionInfo(False),
            },
        )
    )
    options_templates.update(
        options_section(
            ("atlas_autoprompt", "Forge Atlas — Автопромпт", "ui"),
            {
                "atlas_autoprompt_model_dir": OptionInfo(str(Path(paths.models_path) / "AutoPrompt" / "Florence-2-base-ft"), "Каталог Florence-2"),
                "atlas_autoprompt_device": OptionInfo("CPU", "Устройство для Autoprompt", gr.Radio, {"choices": ("CPU", "GPU")}).info("CPU не занимает VRAM Forge; GPU используется только по твоему явному выбору."),
                "atlas_autoprompt_retention_minutes": OptionInfo(10, "Хранить Florence в RAM, минут", gr.Slider, {"minimum": 0, "maximum": 120, "step": 1}),
                "atlas_autoprompt_max_length": OptionInfo(320, "Максимальная длина tile-safe prompt", gr.Slider, {"minimum": 80, "maximum": 800, "step": 10}),
                "atlas_autoprompt_show_raw": OptionInfo(True, "Показывать исходное описание Florence").needs_reload_ui(),
            },
        )
    )
    options_templates.update(
        options_section(
            ("atlas_large_upscale", "Forge Atlas — Большое улучшение", "ui"),
            {
                "atlas_proxy_max_side": OptionInfo(2048, "Максимальная сторона proxy", gr.Slider, {"minimum": 512, "maximum": 4096, "step": 128}),
                "atlas_proxy_max_payload_mb": OptionInfo(12, "Максимальный payload proxy, МиБ", gr.Slider, {"minimum": 2, "maximum": 64, "step": 1}),
                "atlas_upscale_temp_dir": OptionInfo("", "Каталог временных тайлов").info("Пустое значение использует системный TEMP."),
                "atlas_assembly_block_size": OptionInfo(2048, "Размер блока сборки", gr.Radio, {"choices": (512, 1024, 2048, 4096)}),
                "atlas_keep_temp_on_error": OptionInfo(True, "Сохранять тайлы после ошибки для продолжения"),
                "atlas_upscale_output_dir": OptionInfo("", "Папка результатов").info("Пустое значение использует стандартную папку img2img."),
                "atlas_default_tile_preset": OptionInfo("Автоматически", "Тайлы по умолчанию", gr.Radio, {"choices": ("Автоматически", "768 px", "1024 px", "1536 px")}),
            },
        )
    )
    options_templates.update(
        options_section(
            ("atlas_interface", "Forge Atlas — Интерфейс", "ui"),
            {
                "atlas_default_upscale_mode": OptionInfo("Улучшение изображения", "Режим вкладки «Улучшение» по умолчанию", gr.Radio, {"choices": ("Улучшение изображения", "Классический img2img")}).needs_reload_ui(),
                "atlas_show_classic_img2img": OptionInfo(True, "Показывать классический img2img").needs_reload_ui(),
                "atlas_compact_cards": OptionInfo(False, "Компактные карточки Forge Atlas").needs_reload_ui(),
            },
        )
    )
    options_templates.update(
        options_section(
            ("ui_forgecanvas", "Forge Canvas", "ui"),
            {
                "forge_canvas_height": OptionInfo(512, "Canvas Height").info("in pixels").needs_reload_ui(),
                "forge_canvas_toolbar_always": OptionInfo(False, "Always Visible Toolbar").info("disabled: toolbar only appears when hovering the canvas").needs_reload_ui(),
                "forge_canvas_consistent_brush": OptionInfo(False, "Fixed Brush Size").info("disabled: the brush size is <b>pixel-space</b>, the brush stays small when zoomed out ; enabled: the brush size is <b>canvas-space</b>, the brush stays big when zoomed in").needs_reload_ui(),
                "forge_canvas_plain": OptionInfo(False, "Plain Background").info("disabled: checkerboard pattern ; enabled: solid color").needs_reload_ui(),
                "forge_canvas_plain_color": OptionInfo("#808080", "Solid Color for Plain Background", FormColorPicker, {}).needs_reload_ui(),
            },
        )
    )
