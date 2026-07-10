# Forge Neo architecture and extension map

## Audit scope and freshness

This map was verified against Forge Atlas commit `a6e612fdb707151937f4eaf180c9467dc57004c5`
and upstream Forge Neo commit `644450e8bf2df24f0ba87307604d0e9f4ae3a9f7`
(`k_predictor`, 2026-07-10). At audit time Atlas was one commit ahead and upstream had no
additional commits. Re-fetch `upstream/neo` and re-check the affected call path before using
this document after upstream changes.

This is a code map, not a promise that internal APIs remain stable. Prefer the public script
and callback contracts below whenever they can express the requested behavior.

## Layer map

| Layer | Primary locations | Responsibility | Change risk |
| --- | --- | --- | --- |
| Bootstrap | `launch.py`, `modules/launch_utils.py` | Environment preparation and process start | High |
| Runtime startup | `webui.py`, `modules/initialize.py`, `modules/initialize_util.py` | Forge initialization, scripts, Gradio/FastAPI lifecycle | High |
| UI composition | `modules/ui.py`, `modules/ui_toprow.py`, `modules/ui_common.py` | Core tabs, controls, events, output panels | Medium-high |
| Gradio adaptation | `modules/gradio_extensions.py`, `modules/ui_gradio_extensions.py`, `modules/shared_gradio_themes.py`, `style.css`, `javascript/` | Compatibility patches, CSS/JS injection, themes | Medium-high |
| Extension contracts | `modules/scripts.py`, `modules/script_callbacks.py`, `modules/scripts_postprocessing.py`, `modules/extensions.py` | Discoverable scripts, lifecycle callbacks, tabs/settings/postprocessors | Preferred extension surface |
| User settings and presets | `modules/options.py`, `modules/shared_options.py`, `modules_forge/presets.py`, `modules_forge/main_entry.py` | Persistent options and per-family selections | Medium |
| Request adapters | `modules/txt2img.py`, `modules/img2img.py`, `modules/postprocessing.py`, `modules/api/api.py` | UI/API inputs to processing objects | Medium |
| Shared processing | `modules/processing.py` | Model reload, conditioning, sampling, decode, callbacks, saving | High |
| Model selection | `modules_forge/main_entry.py`, `modules/sd_models.py` | Checkpoint/modules/dtype selection and reload trigger | High |
| Model recognition/loading | `modules_forge/packages/huggingface_guess/`, `backend/loader.py`, `backend/huggingface/` | State-dict detection, component split and construction | Very high |
| Family engines | `backend/diffusion_engine/` | Family-specific conditioning, encode/decode and compatibility flags | Very high |
| Sampling/inference | `backend/sampling/`, `backend/modules/`, `modules/sd_samplers*` | Predictor, noise schedule, CFG and sampler behavior | Do not modify without reference-led model work |
| Model patching/memory | `backend/patcher/`, `backend/memory_management.py`, `backend/operations.py` | VRAM/RAM placement, patchers, LoRA, VAE tiling | Very high |
| Upscalers | `modules/upscaler.py`, `modules/modelloader.py`, `modules/esrgan_model.py` | Spandrel/ESRGAN and basic image upscalers | Medium-high |
| Image save/metadata | `modules/images.py`, `modules/infotext_utils.py` | Naming, format selection, atomic file save, infotext | High for ultra-large files |

## Startup sequence

```text
launch.py
  -> modules.launch_utils.prepare_environment()
  -> modules.launch_utils.start()
  -> webui.py import
       -> modules_forge.initialization.initialize_forge()
       -> modules.initialize.imports()
       -> modules.initialize.check_versions()
       -> modules.initialize.initialize()
            -> sd_models.setup_model()
            -> initialize_rest()
                 -> samplers, extensions, checkpoints, localizations
                 -> scripts.load_scripts()
                 -> modelloader.load_upscalers()
                 -> VAE/UNet/extra-networks registration
  -> webui.webui_worker()
       -> script_callbacks.before_ui_callback()
       -> modules.ui.create_ui()
       -> Gradio queue and launch
       -> middleware, progress API, internal UI API, optional public API
       -> script_callbacks.app_started_callback(demo, app)
```

UI reload repeats `initialize_rest(reload_script_modules=True)`, clears and reloads script
callbacks, and rebuilds the Gradio tree. Extension state must therefore be reversible through
`on_before_reload`/`on_script_unloaded` when it patches global objects.

## Gradio composition and styling

`modules.ui.create_ui()` constructs nested `gr.Blocks` for txt2img, img2img, Extras, PNG
Info, Checkpoint Merger, Settings, and Extensions. It appends tuples returned by
`script_callbacks.ui_tabs_callback()`, sorts them with `opts.ui_tab_order`, and renders them
inside the root `gr.Tabs(elem_id="tabs")`.

The root block uses `shared.gradio_theme`. `modules.shared_gradio_themes.reload_gradio_theme()`
loads the default or cached Hub theme. `modules.ui_gradio_extensions` injects:

- root and extension `javascript/*.js` and `javascript/*.mjs`;
- every root/extension `style.css`;
- optional data-path `user.css`.

`modules.gradio_extensions` patches Gradio 4.40.0 component construction. It adds a
`gradio-<block-name>` class and invokes global and current-script before/after component
callbacks. This patch is a compatibility boundary: upgrading Gradio requires a dedicated
migration audit.

Preferred UI approaches, in order:

1. Add a self-contained tab through `script_callbacks.on_ui_tabs`.
2. Add settings through `script_callbacks.on_ui_settings` and `shared.opts.add_option`.
3. Add img2img/txt2img controls through a `modules.scripts.Script`.
4. Add Extras stages through `ScriptPostprocessing`.
5. Style stable `elem_id`/`elem_classes` in an extension/root `style.css`.
6. Use `on_after_component` only when a component contract cannot be expressed directly.

Do not control another tab by programmatically clicking hidden elements. Core component IDs
are useful for CSS and component callbacks but are not a processing API.

## Script and callback contracts

### Discoverable extension files

`modules.scripts.list_scripts()` discovers root and enabled-extension files by convention:

- `scripts/*.py` for `Script` and `ScriptPostprocessing` subclasses;
- `javascript/*.js` and `javascript/*.mjs`;
- `style.css`;
- `localizations/*.json`.

Extension metadata can declare `Requires`, `Before`, and `After`; scripts are topologically
sorted. Built-in processing scripts in `modules/processing_scripts/*.py` are loaded without
extension discovery.

### `modules.scripts.Script`

Use a selectable script for an alternate complete txt2img/img2img workflow, as existing
`scripts/sd_upscale.py` does. Use `scripts.AlwaysVisible` for behavior that participates in
the normal processing flow. Important hooks include:

- `ui`, `show`, `run`;
- `before_process`, `process`;
- `before_process_batch`, `process_batch`;
- `after_extra_networks_activate`, `process_before_every_sampling`;
- `post_sample`, `postprocess_batch`, `postprocess_batch_list`;
- `postprocess_image`, `postprocess_maskoverlay`, `postprocess_image_after_composite`;
- `postprocess`, `before_hr`;
- component callbacks registered by `on_before_component`/`on_after_component` on a script.

Script UI controls are assigned stable argument slices (`args_from:args_to`) and are also
described to the API. Do not reorder or delete existing script arguments without considering
infotext and API compatibility.

### `ScriptPostprocessing`

Use `modules.scripts_postprocessing.ScriptPostprocessing` for Extras pipeline stages.
`ScriptPostprocessingRunner` orders stages, creates their UI, and passes a mutable
`PostprocessedImage` with `image`, `info`, `shared`, and `extra_images`.

### Global callbacks

`modules.script_callbacks` exposes registered callbacks for:

- lifecycle: `on_before_ui`, `on_ui_tabs`, `on_ui_settings`, `on_app_started`,
  `on_before_reload`, `on_script_unloaded`;
- models and UI: `on_model_loaded`, `on_before_component`, `on_after_component`,
  `on_list_unets`, `on_list_optimizers`, `on_before_token_counter`;
- generation: `on_extra_noise`, `on_cfg_denoiser`, `on_cfg_denoised`, `on_cfg_after_cfg`;
- results: `on_before_image_saved`, `on_image_saved`, `on_image_grid`,
  `on_infotext_pasted`.

Callback order can be controlled by extension metadata and user priority settings. Do not
assume filesystem discovery order is the execution order.

## Generation request flow

### txt2img

```text
modules.ui submit event
  -> call_queue.wrap_gradio_gpu_call(modules.txt2img.txt2img)
  -> main_thread.run_and_wait_result(txt2img_function)
  -> txt2img_create_processing() -> StableDiffusionProcessingTxt2Img
  -> selected Script.run(), or processing.process_images()
```

### img2img

```text
modules.ui submit event
  -> call_queue.wrap_gradio_gpu_call(modules.img2img.img2img)
  -> main_thread.run_and_wait_result(img2img_function)
  -> StableDiffusionProcessingImg2Img
  -> selected Script.run(), or processing.process_images()
```

Batch img2img is handled by `modules.img2img.process_batch()`. It repeatedly reuses the
processing object and can optionally limit images returned to the UI. A new Atlas workflow
should reuse processing objects/contracts but must not assume that the existing UI response
can carry an ultra-large result.

### Shared processing core

`modules.processing.process_images()`:

1. runs `before_process`;
2. applies temporary setting overrides;
3. calls `manage_model_and_prompt_cache()`/`sd_models.forge_model_reload()`;
4. validates sampler/scheduler;
5. delegates to `process_images_inner()`;
6. restores options and VAE overrides.

`process_images_inner()` performs prompts/seeds, model flags, LoRA/extra networks,
conditioning, sampling, VAE decode, postprocessing hooks, metadata, image saving, optional
grids/video, and returns a `Processed` containing PIL images. It is the shared txt2img and
img2img engine and is a high-risk change surface.

`modules.call_queue.wrap_gradio_gpu_call()` serializes GPU jobs with `queue_lock`, manages
`shared.state`, progress results, exceptions, timing, and memory statistics. Long-running
Atlas jobs should preserve this contract or introduce an explicit job service with equivalent
cancellation/progress behavior; do not bypass the GPU lock accidentally.

## Model selection, presets, and reload

`modules_forge.main_entry.make_checkpoint_manager_ui()` owns the top model controls:

- `forge_ui_preset`;
- `setting_sd_model_checkpoint`;
- `setting_sd_modules` (VAE/text encoders, multiselect);
- `forge_ui_dtype`.

`modules_forge.main_entry.forge_main_entry()` connects them to the standard txt2img/img2img
controls through registered infotext fields. Per-family checkpoint, additional modules,
dtype, steps, sampler, scheduler, dimensions, CFG/shift/distilled CFG, and batch/frame values
are persisted by `modules_forge.presets.register()`.

The reload path is:

```text
checkpoint_change/modules_change/dtype_change
  -> shared.opts and per-preset options
  -> refresh_model_loading_parameters()
  -> sd_models.model_data.forge_loading_parameters
  -> processing.need_global_unload = True
  -> next process_images()
  -> sd_models.forge_model_reload()
  -> backend.loader.forge_loader()
```

A new task-oriented UI must bind to or call these functions/contracts. Duplicating model
state in a separate tab risks using a displayed selection that differs from the model loaded
by `process_images()`.

## Model recognition and construction

`backend.loader.split_state_dict()` loads checkpoint and additional modules, converts
quantization, guesses architecture from state-dict structure, merges/replaces components,
sets clip/model type and ztsnr, and separates UNet/DiT, VAE, and text encoder components.

Recognition definitions live in:

- `modules_forge/packages/huggingface_guess/detection.py` for structural detection;
- `model_list.py` for family configuration, repository/config mapping, prefixes, latent
  format, model type, and component targets;
- `backend/huggingface/<org>/<model>/` for local Diffusers component configurations.

`backend.loader.forge_loader()` then sets dynamic compatibility flags, loads components from
the local Diffusers configuration, sets scheduler prediction type, and selects a class from
`possible_models`. The engine classes are in `backend/diffusion_engine/` and subclass
`ForgeDiffusionEngine`.

Adding a truly new family can therefore touch several coordinated surfaces:

1. official/reference-led state-dict detection and model config;
2. local Hugging Face/Diffusers configuration files;
3. component constructors in `load_huggingface_component` if types are new;
4. a family engine for conditioning/encode/decode behavior;
5. `possible_models` registration;
6. presets and UI visibility;
7. tests for reload/switching and missing components.

Filename-derived flags currently exist for Kontext, Qwen Edit, and SDXL rectified-flow, while
Klein/Wan/PiD are inferred from the guessed repository. Preserve compatibility but prefer
structural or metadata detection when introducing new support.

Never modify `backend/sampling`, prediction types, scheduler behavior, conditioning, latent
formats, or family engines merely to make an unknown checkpoint run. Use the model-integration
research contract first.

## Memory and patcher boundary

`backend.memory_management` owns loaded-model tracking, freeing, full/partial loading,
offload, cleanup, cache clearing, and VRAM states. `backend.patcher.ModelPatcher` and its
UNet/VAE/CLIP derivatives carry patches and device behavior. Family engines expose
`ForgeObjects` containing UNet, CLIP, VAE, and CLIP Vision patchers.

Extensions should use the existing patcher/memory APIs. Direct `.to("cuda")`, permanent
global model references, or parallel uncoordinated GPU work can break offload and model
switching.

## Extras and SD Upscale: current behavior and limits

### SD Upscale

`scripts/sd_upscale.py` is a selectable img2img `Script`. Its current algorithm:

1. upscales the entire source through `upscaler.scaler.upscale()`;
2. calls `modules.images.split_grid()`, which crops and stores every tile as a PIL image;
3. builds a second `work` list of all tile images;
4. processes batches through `processing.process_images()` and accumulates all results in
   `work_results`;
5. writes results back into the grid;
6. calls `modules.images.combine_grid()`, which creates full-width rows and a full-size RGB
   output image;
7. returns full result images inside `Processed` for Gradio.

This is a correct reuse example for model processing and selection, but it is not a bounded-
memory or disk-backed architecture. It must not be scaled to arbitrary dimensions merely by
raising sliders.

### Extras

`modules.ui_postprocessing` sends a PIL source and receives a gallery. `modules.postprocessing`
loads each full image, runs `ScriptPostprocessingRunner`, saves it, assigns it as the current
preview, and appends the full PIL result unless directory mode hides results.

`scripts/postprocessing_upscale.py` calls a full-image upscaler and caches full output images;
its UI currently exposes a `Max Side Length` slider capped at 8192. This cap is a UI/current-
implementation detail, not an Atlas product limit. Removing it without replacing the
full-image implementation would be unsafe.

### Image saving

`modules.images.save_image()` selects format, applies JPEG/WebP dimension fallbacks, calls
save callbacks, and writes through a temporary file followed by `os.replace`. It still
accepts a complete PIL image, so atomic naming and metadata behavior can be reused, but the
pixel encoder path is not streaming. A disk-backed Atlas writer needs a compatible metadata,
callback, naming, collision, and finalization contract rather than blindly calling
`save_image()` with a giant PIL object.

## Recommended Atlas extension boundary

For a new ultra-large task-oriented workflow:

- create a self-contained Atlas tab through `on_ui_tabs` or a built-in extension;
- reuse `modules_forge.main_entry` as the single source of model/module/preset selection;
- create normal `StableDiffusionProcessingImg2Img` jobs per bounded tile and execute them
  through the existing queue/processing contract;
- implement a separate disk-backed tile source, work manifest, assembler/writer, proxy
  preview, cancellation, cleanup, and resume layer;
- return only job metadata, paths, and bounded previews to Gradio;
- preserve infotext/model hashes and save callbacks through an explicit large-artifact
  adapter;
- keep original txt2img, img2img, SD Upscale, and Extras behavior intact during the first
  implementation slice.

Do not begin by rewriting `modules.processing`, `backend.sampling`, or family engines. The
first architectural seam is around input tiling, job orchestration, disk assembly, and UI
response shape.

## API surfaces

`modules.api.api.Api` exposes `/sdapi/v1` txt2img, img2img, Extras, progress, interrupt,
options, samplers/schedulers, upscalers, checkpoints/modules, memory, scripts, and extensions.
`webui.py` optionally installs it when `--api` is enabled.

Extensions can register FastAPI routes using `script_callbacks.on_app_started(demo, app)`.
An Atlas job API should use a namespaced route, validate local paths carefully, preserve
authentication behavior, and avoid returning full-resolution base64 images.

## Verification reality

No repository test suite or pytest/unittest configuration was found during this audit.
Changes therefore need focused tests added with the new code plus proportionate manual smoke
checks. At minimum preserve:

- clean startup and UI reload;
- txt2img and img2img baseline generation;
- model/module/preset selection and switching;
- selected and always-on scripts;
- Extras and ordinary SD Upscale;
- API behavior when affected;
- cancellation, progress, saving, metadata, and cleanup.

## Re-audit triggers

Re-audit relevant sections when upstream changes any of:

- Gradio version or `modules/gradio_extensions.py`;
- `modules.ui.create_ui`, script discovery, or callback maps;
- `StableDiffusionProcessing*` or `process_images*`;
- `modules_forge.main_entry` or presets;
- `backend.loader`, `huggingface_guess`, `possible_models`, or family engines;
- memory management/patchers;
- `scripts/sd_upscale.py`, postprocessing upscale, or image saving.
