---
name: forge-atlas-large-upscale
description: Design, implement, diagnose, or review Forge Atlas SD Upscale, img2img, Extras, tiling, and arbitrarily large disk-backed output workflows without hardcoded dimension limits. Use for upscale UI reorganization, model-noise/detail passes, tile assembly, previews, memory or disk constraints, output formats, progress, cancellation, recovery, and preservation of checkpoint, VAE, text encoder, sampler, scheduler, and preset choices.
---

# Forge Atlas Large Upscale

Read `references/large-image-contract.md` before changing code or UI.

## Workflow

1. Inspect the existing SD Upscale, img2img, Extras, postprocessing, save, and preset paths.
2. Preserve explicit model and additional-module selection. Reuse the existing processing
   objects rather than invoking controls in another tab.
3. Separate the bounded browser preview from the full-resolution artifact.
4. Calculate pixel count, working-set estimates, temporary disk use, tile count, overlap,
   and output-format constraints before starting.
5. Process and assemble incrementally with bounded RAM/VRAM. Avoid full-size base64,
   browser canvas, gallery payloads, and unnecessary image copies.
6. Provide progress, cancellation, cleanup, actionable errors, output path, dimensions,
   file size, and a small proxy preview.
7. Test seams, color/profile preservation, failure cleanup, and model switching.

Do not impose a product-level maximum dimension. If a selected encoder, file format,
filesystem, dependency, or processing strategy has a real limit, detect and explain that
specific limit instead of substituting an arbitrary global cap.

## UI principles

- Optimize the primary path for selecting an image, target dimensions, upscale method,
  denoising/detail strength, model/modules, tile settings, and output.
- Keep advanced settings accessible without hiding user selections behind automation.
- Do not prioritize before/after comparison; it is optional and must use proxies only.
- Never load the completed full-resolution image into Gradio.
