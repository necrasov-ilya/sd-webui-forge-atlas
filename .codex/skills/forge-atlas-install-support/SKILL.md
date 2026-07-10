---
name: forge-atlas-install-support
description: Create, simplify, diagnose, or review Forge Atlas installation, first launch, updates, rollback, Windows launchers, Python or uv environments, PyTorch/CUDA compatibility, FFmpeg, attention packages, model placement, shortcuts, and support reports. Use whenever setup or environment changes must remain reproducible for a non-technical user.
---

# Forge Atlas Install Support

## Workflow

1. Inspect current Forge Neo installation documentation and dependency pins before changing
   setup behavior. Do not assume the newest Python, PyTorch, CUDA, or package is compatible.
2. Collect OS, GPU and driver, VRAM/RAM, free disk, repository revision, Python environment,
   launch arguments, and relevant logs without exposing secrets.
3. Prefer `uv` and existing launch infrastructure when supported by the current upstream.
4. Make setup idempotent: detect existing tools and environments before installing or
   replacing them. Explain migrations and keep a rollback path.
5. Separate core installation from optional acceleration packages and model downloads.
   Never install every attention backend by default.
6. For model bundles, show official source, license/gating, exact components, total download
   size, destination, and hardware expectation before requesting confirmation.
7. Verify clean install or a safe equivalent, first launch, second launch, update behavior,
   paths with spaces and Cyrillic characters, and generation smoke test when hardware permits.

## User-facing behavior

- Use plain Russian messages with a concise suggested fix.
- Generate a copyable diagnostic report with secrets and tokens redacted.
- Do not delete models, outputs, presets, or user configuration during repair or update.
- Do not hide errors or continue after an incompatible foundational dependency is detected.
