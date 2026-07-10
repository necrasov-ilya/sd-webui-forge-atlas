# Forge Atlas project instructions

Forge Atlas is an independent, modified distribution based on the `neo` branch of
`Haoming02/sd-webui-forge-classic`. Preserve the upstream architecture and keep the
product usable by a non-technical Windows user.

## Source and branch policy

- Treat `origin` as the Forge Atlas fork and `upstream` as Forge Neo.
- Before architecture, model-support, dependency, installation, or UI work, fetch and
  inspect the current upstream `neo` branch, its recent releases, Wiki, and relevant issues.
- Do not overwrite user changes. Keep changes small enough to rebase onto upstream.
- Prefer adapters, callbacks, shared components, settings, and existing processing APIs
  over copied pipelines or DOM automation.
- Do not upgrade Gradio, PyTorch, CUDA dependencies, or core inference libraries as a
  side effect of unrelated work.

## Inference is reference-led

- Never invent or casually rewrite inference, sampling loops, scheduler formulas,
  timestep/sigma/shift behavior, CFG/guidance semantics, conditioning, or latent scaling.
- Research current primary implementations before proposing or changing model support.
  Use official model repositories/model cards first, then current Forge Neo, official
  Diffusers integrations, and maintained ComfyUI implementations.
- Record source URLs, dates, versions or commits, model revisions, required components,
  supported dtypes/quantizations, and known limitations.
- Identify the smallest missing integration layer and adapt it to Forge memory management.
- If evidence is incomplete or sources disagree, stop and report the uncertainty. An
  explicit unsupported-model error is better than silently using a similar architecture.
- Do not infer architecture solely from a filename when state-dict keys or metadata can
  identify it reliably. Preserve compatible filename fallbacks when upstream needs them.
- Do not claim support from one successful generation. Test loading, generation,
  unloading/switching, metadata, relevant img2img/refiner paths, and constrained VRAM.

## User experience

- Preserve explicit checkpoint, VAE, text encoder, additional module, sampler, scheduler,
  and preset selection. Do not replace user choices with opaque automatic selection.
- Use Russian-friendly, plain labels and actionable errors where the user-facing surface
  is intended for the primary user.
- Keep advanced controls available, but make common workflows possible without knowing
  internal diffusion terminology.
- Style Gradio through its pinned theme tokens, repository CSS, and stable component IDs or
  classes. Do not depend on brittle scripts that click hidden controls in other tabs.

## Ultra-large image workflows

- Treat arbitrarily large, disk-backed outputs as a core use case, not an edge case. Do not
  introduce a fixed dimension or pixel-count ceiling unless a verified external format,
  library, filesystem, or algorithm limit requires it; report that limit explicitly.
- Never send or render the full-resolution result in the browser. Generate a bounded proxy
  preview and expose the full output as an on-disk artifact.
- Avoid base64 duplication and full-image copies. Prefer tiled or streamed processing,
  bounded memory, incremental disk assembly, cleanup, progress reporting, and recovery.
- Validate dimensions, pixel count, format limits, disk space, RAM/VRAM estimates, overlap,
  seams, color profile, metadata, cancellation, and partial-file behavior.

## Installation and distribution

- Optimize for a reproducible Windows installation using the versions supported by current
  Forge Neo. Detect the environment before changing it and explain destructive choices.
- Never download large model bundles without showing source, license, components, total
  size, destination, and obtaining confirmation. Support gated downloads explicitly.
- Preserve AGPL-3.0 notices and make corresponding source available to users, including
  network users of a modified build. Check model and asset licenses separately.

## Verification

- Run the narrowest relevant tests plus import/startup checks for touched areas.
- For UI changes, verify both light and dark themes and common viewport sizes.
- For large-image changes, test with synthetic dimensions without allocating an unsafe
  full-resolution buffer, then run a bounded end-to-end tile test.
- Document any test that cannot be run and why.

## Repository skills

- Use `.codex/skills/forge-atlas-core` for general implementation and review.
- Use `.codex/skills/forge-atlas-model-integration` for model families and inference.
- Use `.codex/skills/forge-atlas-large-upscale` for SD Upscale, Extras, tiling, and ultra-large outputs.
- Use `.codex/skills/forge-atlas-install-support` for setup, updates, dependencies, and diagnostics.
