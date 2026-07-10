# Ultra-large image contract

## Scale assumptions

Output dimensions are user-defined and have no Forge Atlas hardcoded upper bound. Memory,
temporary storage, output format, encoder, filesystem, and algorithm constraints must be
calculated from the requested job. Estimate decoded buffers from width, height, channels,
bit depth, copies, latents, tiles, overlap, and encoder behavior. Treat any design requiring
multiple full decoded buffers as unsafe by default.

## Required properties

- Bound preview dimensions and encoded payload independently of output dimensions.
- Store the full result on disk and return metadata plus a proxy, not the full pixel payload.
- Use incremental or memory-mapped assembly where supported and document format behavior.
- Do not add a fixed maximum width, height, or pixel count. Detect and report only verified
  limits imposed by the selected format, encoder, library, filesystem, or processing path.
- Preflight target dimensions, pixel count, RAM/VRAM, temporary and final disk space, tile
  count, overlap, path, filesystem, encoder limits, and Pillow safety behavior.
- Preserve color mode, ICC profile, alpha, orientation, and generation metadata where the
  selected format supports them.
- Write to a temporary artifact and finalize atomically when practical. Clean partial files
  on cancellation or clearly mark resumable state.
- Avoid unbounded queues and retaining processed tiles after they are committed.

## Verification

- Unit-test calculations across small, large, and extreme synthetic dimensions without
  allocating full-resolution images; include values above ordinary browser canvas limits.
- End-to-end test with a bounded synthetic tiled image and low-cost processing stub.
- Exercise cancellation, out-of-disk simulation, encoder failure, odd edge tiles, overlap,
  model switching, and preview generation.
- Inspect seams and coordinate correctness, not only completion.
