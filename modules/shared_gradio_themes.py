import gradio as gr
from gradio.themes.utils import colors

from modules import errors, shared


ATLAS_THEME_NAME = "Forge Atlas"
ATLAS_ACCENT = colors.Color(
    name="atlas",
    c50="#fff1f5",
    c100="#ffe4ec",
    c200="#ffc9d8",
    c300="#f5a0bb",
    c400="#dc678e",
    c500="#AC2954",
    c600="#982149",
    c700="#7d1b3d",
    c800="#651833",
    c900="#4d1529",
    c950="#2d0b17",
)
ATLAS_NEUTRAL = colors.Color(
    name="atlas-neutral",
    c50="#faf8fb",
    c100="#f0edf2",
    c200="#dcd6df",
    c300="#bdb4c1",
    c400="#998e9e",
    c500="#776d7c",
    c600="#5a505f",
    c700="#403746",
    c800="#2a242f",
    c900="#19161d",
    c950="#0e0c11",
)


def create_atlas_theme() -> gr.themes.ThemeClass:
    theme = gr.themes.Base(
        primary_hue=ATLAS_ACCENT,
        secondary_hue=ATLAS_ACCENT,
        neutral_hue=ATLAS_NEUTRAL,
        spacing_size="md",
        radius_size="md",
        text_size="md",
        font=["Source Sans Pro", "ui-sans-serif", "system-ui", "sans-serif"],
        font_mono=["IBM Plex Mono", "ui-monospace", "Consolas", "monospace"],
    )
    theme.name = "forge-atlas"

    return theme.set(
        body_background_fill="#0e0c11",
        body_background_fill_dark="#0e0c11",
        body_text_color="#f4eff6",
        body_text_color_dark="#f4eff6",
        body_text_color_subdued="#a99eae",
        body_text_color_subdued_dark="#a99eae",
        background_fill_primary="#0e0c11",
        background_fill_primary_dark="#0e0c11",
        background_fill_secondary="#17131a",
        background_fill_secondary_dark="#17131a",
        border_color_primary="transparent",
        border_color_primary_dark="transparent",
        border_color_accent="#AC2954",
        border_color_accent_dark="#AC2954",
        border_color_accent_subdued="rgba(172, 41, 84, 0.35)",
        border_color_accent_subdued_dark="rgba(172, 41, 84, 0.35)",
        color_accent="#AC2954",
        color_accent_soft="rgba(172, 41, 84, 0.16)",
        color_accent_soft_dark="rgba(172, 41, 84, 0.16)",
        link_text_color="#df789c",
        link_text_color_dark="#df789c",
        link_text_color_hover="#f0a0bc",
        link_text_color_hover_dark="#f0a0bc",
        link_text_color_active="#AC2954",
        link_text_color_active_dark="#AC2954",
        link_text_color_visited="#c98aa2",
        link_text_color_visited_dark="#c98aa2",
        shadow_drop="0 8px 24px rgba(0, 0, 0, 0.18)",
        shadow_drop_lg="0 18px 48px rgba(0, 0, 0, 0.28)",
        shadow_inset="none",
        block_background_fill="#19151c",
        block_background_fill_dark="#19151c",
        block_border_color="transparent",
        block_border_color_dark="transparent",
        block_border_width="0px",
        block_border_width_dark="0px",
        block_radius="14px",
        block_shadow="none",
        block_shadow_dark="none",
        block_label_background_fill="#211b24",
        block_label_background_fill_dark="#211b24",
        block_label_border_color="transparent",
        block_label_border_color_dark="transparent",
        block_label_border_width="0px",
        block_label_border_width_dark="0px",
        block_label_radius="10px",
        block_label_text_color="#cfc5d2",
        block_label_text_color_dark="#cfc5d2",
        block_title_background_fill="transparent",
        block_title_background_fill_dark="transparent",
        block_title_border_color="transparent",
        block_title_border_color_dark="transparent",
        block_title_border_width="0px",
        block_title_border_width_dark="0px",
        block_title_text_color="#f4eff6",
        block_title_text_color_dark="#f4eff6",
        block_title_text_weight="600",
        container_radius="16px",
        panel_background_fill="#151218",
        panel_background_fill_dark="#151218",
        panel_border_color="transparent",
        panel_border_color_dark="transparent",
        panel_border_width="0px",
        panel_border_width_dark="0px",
        accordion_text_color="#f4eff6",
        accordion_text_color_dark="#f4eff6",
        input_background_fill="#211b24",
        input_background_fill_dark="#211b24",
        input_background_fill_focus="#27202b",
        input_background_fill_focus_dark="#27202b",
        input_background_fill_hover="#27202b",
        input_background_fill_hover_dark="#27202b",
        input_border_color="transparent",
        input_border_color_dark="transparent",
        input_border_color_focus="transparent",
        input_border_color_focus_dark="transparent",
        input_border_color_hover="transparent",
        input_border_color_hover_dark="transparent",
        input_border_width="0px",
        input_border_width_dark="0px",
        input_radius="12px",
        input_shadow="none",
        input_shadow_dark="none",
        input_shadow_focus="0 0 0 2px rgba(172, 41, 84, 0.58)",
        input_shadow_focus_dark="0 0 0 2px rgba(172, 41, 84, 0.58)",
        input_placeholder_color="#807586",
        input_placeholder_color_dark="#807586",
        checkbox_background_color="#2a232e",
        checkbox_background_color_dark="#2a232e",
        checkbox_background_color_selected="#AC2954",
        checkbox_background_color_selected_dark="#AC2954",
        checkbox_border_color="transparent",
        checkbox_border_color_dark="transparent",
        checkbox_border_color_selected="transparent",
        checkbox_border_color_selected_dark="transparent",
        checkbox_border_width="0px",
        checkbox_border_width_dark="0px",
        checkbox_label_background_fill="#211b24",
        checkbox_label_background_fill_dark="#211b24",
        checkbox_label_background_fill_hover="#2a222e",
        checkbox_label_background_fill_hover_dark="#2a222e",
        checkbox_label_background_fill_selected="rgba(172, 41, 84, 0.22)",
        checkbox_label_background_fill_selected_dark="rgba(172, 41, 84, 0.22)",
        checkbox_label_border_color="transparent",
        checkbox_label_border_color_dark="transparent",
        checkbox_label_border_color_hover="transparent",
        checkbox_label_border_color_hover_dark="transparent",
        checkbox_label_border_width="0px",
        checkbox_label_border_width_dark="0px",
        checkbox_label_shadow="none",
        loader_color="#AC2954",
        loader_color_dark="#AC2954",
        slider_color="#AC2954",
        slider_color_dark="#AC2954",
        button_border_width="0px",
        button_border_width_dark="0px",
        button_shadow="none",
        button_shadow_active="0 3px 12px rgba(0, 0, 0, 0.24) inset",
        button_shadow_hover="0 10px 24px rgba(0, 0, 0, 0.22)",
        button_transition="transform 140ms ease, background-color 140ms ease, box-shadow 140ms ease",
        button_large_radius="12px",
        button_small_radius="10px",
        button_primary_background_fill="#AC2954",
        button_primary_background_fill_dark="#AC2954",
        button_primary_background_fill_hover="#c43a68",
        button_primary_background_fill_hover_dark="#c43a68",
        button_primary_border_color="transparent",
        button_primary_border_color_dark="transparent",
        button_primary_border_color_hover="transparent",
        button_primary_border_color_hover_dark="transparent",
        button_primary_text_color="#ffffff",
        button_primary_text_color_dark="#ffffff",
        button_primary_text_color_hover="#ffffff",
        button_primary_text_color_hover_dark="#ffffff",
        button_secondary_background_fill="#28212c",
        button_secondary_background_fill_dark="#28212c",
        button_secondary_background_fill_hover="#352c3a",
        button_secondary_background_fill_hover_dark="#352c3a",
        button_secondary_border_color="transparent",
        button_secondary_border_color_dark="transparent",
        button_secondary_border_color_hover="transparent",
        button_secondary_border_color_hover_dark="transparent",
        button_secondary_text_color="#eee8f0",
        button_secondary_text_color_dark="#eee8f0",
        button_secondary_text_color_hover="#ffffff",
        button_secondary_text_color_hover_dark="#ffffff",
        button_cancel_background_fill="#572138",
        button_cancel_background_fill_dark="#572138",
        button_cancel_background_fill_hover="#722947",
        button_cancel_background_fill_hover_dark="#722947",
        button_cancel_border_color="transparent",
        button_cancel_border_color_dark="transparent",
        button_cancel_border_color_hover="transparent",
        button_cancel_border_color_hover_dark="transparent",
        button_cancel_text_color="#fff1f5",
        button_cancel_text_color_dark="#fff1f5",
        button_cancel_text_color_hover="#ffffff",
        button_cancel_text_color_hover_dark="#ffffff",
    )


def reload_gradio_theme(theme_name=None):
    try:
        shared.gradio_theme = create_atlas_theme()
        if shared.opts is not None:
            shared.opts.data["gradio_theme"] = ATLAS_THEME_NAME
    except Exception:
        errors.report("creating Forge Atlas theme", exc_info=True)
        shared.gradio_theme = gr.themes.Base()

    shared.gradio_theme.sd_webui_modal_lightbox_toolbar_opacity = shared.opts.sd_webui_modal_lightbox_toolbar_opacity
    shared.gradio_theme.sd_webui_modal_lightbox_icon_opacity = shared.opts.sd_webui_modal_lightbox_icon_opacity


def resolve_var(name: str, gradio_theme=None, history=None):
    try:
        if history is None:
            history = []
        if gradio_theme is None:
            gradio_theme = shared.gradio_theme

        name = name.strip()
        name = name[1:] if name.startswith("*") else name

        if name in history:
            raise ValueError(f'Circular references: name "{name}" in {history}')

        if value := getattr(gradio_theme, name, None):
            return resolve_var(value, gradio_theme, history + [name])
        return name
    except Exception:
        initial_name = history[0] if history else name
        errors.report(f"resolve_color({initial_name})", exc_info=True)
        return "#000000" if initial_name.endswith("_dark") else "#ffffff"
