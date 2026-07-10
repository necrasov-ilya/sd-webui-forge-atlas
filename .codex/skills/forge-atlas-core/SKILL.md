---
name: forge-atlas-core
description: Implement or review general Forge Atlas changes while preserving the current Forge Neo architecture, upstream compatibility, explicit user choices, and a non-technical UI. Use for runtime, settings, Gradio UI, shared components, refactors, bug fixes, dependencies, or any cross-cutting repository change that is not exclusively model integration, ultra-large upscale, or installation.
---

# Forge Atlas Core

Read `references/forge-neo-architecture.md` before changing startup, Gradio composition,
scripts/callbacks, processing, model selection/loading, Extras, saving, or APIs. Re-audit the
affected path when `upstream/neo` has moved beyond the revision recorded there.

## Workflow

1. Read the root `AGENTS.md` and inspect the working tree before acting.
2. Locate the existing Forge Neo path for the behavior. Inspect recent upstream `neo`
   changes when the area is unstable or has changed since the fork point.
3. State the compatibility boundary: existing API, callback, processing object, setting,
   component, or extension contract that the change must preserve.
4. Implement the smallest coherent change. Reuse shared components and processing APIs;
   avoid duplicating tabs, pipelines, state, or model loaders.
5. Preserve manual model/module selection and saved presets.
6. Verify the affected workflow and a neighboring workflow that shares the changed code.

## Guardrails

- Do not modify inference merely to make a UI feature work. Route through existing jobs.
- Do not upgrade pinned foundational dependencies without an explicit migration task.
- Do not automate the UI by clicking hidden controls or scraping unstable Gradio markup.
- Add stable `elem_id` or classes when targeted styling is required.
- Keep upstream-facing changes easy to identify and rebase.
- Report assumptions and untested hardware-specific behavior.

## Completion report

Include changed behavior, preserved contracts, upstream evidence consulted when relevant,
tests run, and remaining compatibility risks.
