# Model integration research contract

## Evidence order

1. Official model repository, paper, model card, and inference code.
2. Current `Haoming02/sd-webui-forge-classic` `neo` branch, releases, Wiki, and issues.
3. Official or maintained Diffusers integration.
4. Current ComfyUI core or maintained author implementation.
5. Maintainer discussions and reproducible community evidence.
6. New local implementation only after the preceding sources are exhausted.

Record access date plus release, tag, commit, or model revision. Recheck research older than
30 days and always recheck when upstream moved or the requested model was recently released.

## Decision record

Capture:

- exact model variants and intended tasks;
- checkpoint/DiT, tokenizer, text encoder, vision encoder, VAE, and auxiliary files;
- tensor layout and reliable architecture fingerprints;
- scheduler, timestep/sigma/shift, prediction type, guidance, conditioning, and latent rules;
- supported precision and quantization, device placement, RAM/VRAM, and offload behavior;
- img2img, inpaint, refiner, multi-image, video, LoRA, and ControlNet applicability;
- source URLs, licenses, file sizes, hashes when published, and gated-access requirements;
- upstream gaps, conflicts, failure modes, and rollback boundary.

Separate facts, inference, and recommendation. Do not turn a plausible mapping into a fact.

## Validation matrix

At minimum verify:

- clean load and one representative generation;
- unload, reload, and switching to a different model family;
- deterministic parameter plumbing and infotext/metadata round-trip;
- expected dtype, device placement, and bounded-memory behavior;
- missing/wrong component errors;
- relevant img2img, refiner, video, LoRA, or edit paths;
- an upstream-supported baseline to detect regression.

One successful image is not sufficient evidence of correct model support.
