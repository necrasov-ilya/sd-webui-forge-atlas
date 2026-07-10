---
name: forge-atlas-model-integration
description: Research, evaluate, implement, or review support for diffusion model families and variants in Forge Atlas, including Flux, Flux.2, Flux.2 Klein, Wan, Qwen, checkpoints, DiTs, text and vision encoders, VAEs, LoRAs, quantizations, schedulers, conditioning, and model downloads. Use whenever a task could affect model detection, loading, inference semantics, components, recommended parameters, compatibility, or claims of model support.
---

# Forge Atlas Model Integration

Do not design inference from memory. Read `references/research-contract.md` before any
implementation or support recommendation.

## Required workflow

1. Resolve the exact model, revision, task, weight format, dtype, and quantization.
2. Inspect current upstream Forge Neo before assuming support is absent.
3. Build the evidence ladder in the reference contract. Prefer primary, current sources.
4. Map official components and inference semantics to existing Forge abstractions.
5. Identify the smallest missing adapter. Do not rewrite sampling, scheduling, guidance,
   conditioning, or latent scaling unless the official implementation requires it and no
   maintained compatible implementation exists.
6. Present the source, license, size, required files, folders, hardware expectations, and
   limitations before downloading model assets. Never silently download large weights.
7. Implement explicit detection and actionable incompatibility errors. Prefer metadata or
   state-dict structure over filenames; retain necessary upstream-compatible fallbacks.
8. Validate the matrix in the research contract and document exact revisions tested.

## Stop conditions

Stop and report instead of coding when official semantics are unclear, sources conflict,
required weights are inaccessible, licensing is incompatible, or the only apparent route
requires an unjustified core inference rewrite.
