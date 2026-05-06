# AGENTS.md

## Purpose

This repository is a Dataiku DSS plugin scaffold for exposing the Kiji inspector as a custom guardrail.

The repo has three intended plugin components:

- `parameter-sets/linux-process-settings/`
- `python-runnables/manage-inspector-process/`
- `python-guardrails/pii-guardrail/`

They are scaffold stubs today. Treat the current names and placeholder fields as temporary unless the user says otherwise.

## Working Model

Design changes around this split:

- Parameter set: source of truth for inspector process connection details
- Runnable: operator workflow for start, stop, status, and inspection
- Guardrail: runtime adapter between DSS LLM Mesh and Kiji inspector
- `python-lib/kijiinspector/`: shared implementation used by both runnable and guardrail

Do not duplicate transport or config parsing logic across the runnable and guardrail. Put shared behavior in `python-lib/kijiinspector/`.

## Repo-Specific Expectations

- Keep plugin descriptors in sync with implementation names. If a component is renamed, update both folder names and descriptor metadata.
- Prefer explicit, stable parameter names. This plugin will likely need fields for PID, Unix socket path or port, Kiji version, and possibly startup or health-check options.
- Keep runnable and guardrail modules thin. Business logic belongs in shared library code.
- Preserve compatibility with the DSS plugin structure already in place unless the user asks for a broader refactor.
- When documenting behavior, distinguish clearly between what exists now and what is planned.

## Current Gaps

These are known scaffold leftovers and should not be treated as finished design:

- `pii-guardrail` is a template name, not a Kiji-specific one.
- JSON descriptors still contain placeholder labels, descriptions, and params.
- The runnable raises `unimplemented`.
- The guardrail currently just returns its input.
- `python-lib/kijiinspector/` has no real implementation yet.

## Recommended Implementation Order

1. Finalize the parameter set contract.
2. Implement shared config and connection helpers in `python-lib/kijiinspector/`.
3. Implement runnable actions for lifecycle and status.
4. Implement guardrail request forwarding and response mapping.
5. Add tests or at least executable validation paths for the shared library and guardrail adapter.

## Validation Checklist

Before considering a change complete, verify:

- Descriptor labels and descriptions are no longer template text.
- Component names reflect Kiji, not generic plugin scaffolding.
- Shared code lives under `python-lib/kijiinspector/`.
- The runnable produces actionable operator output.
- The guardrail handles both success and failure paths deterministically.
- Documentation reflects the actual implemented behavior.
