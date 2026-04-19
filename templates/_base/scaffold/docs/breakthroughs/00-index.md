<!-- domain:ALL | layer:index | ssot:true | updated:{{DATE}} -->
# Breakthroughs — Index

Purpose: Human-readable log of breakthrough narratives filed back by `cos_learn_narrative`. Each file captures a non-obvious insight from a rework→success cycle so future work can avoid the same dead-ends.
Read when: Starting a task that touches an area with past breakthroughs, or onboarding to the project.
Skip when: The active task is routine and no related breakthrough is surfaced by `cos_learn_suggest` / `cos_doc_search`.
Read next: The specific breakthrough file relevant to the area you're working on.

> Nav: [Docs Index](../00-index.md)

## How entries are created

Every call to `cos_learn_narrative` writes one markdown file here in addition to the DB record. Files are named `<TASK-ID>-<slug>.md` and are safe to edit by humans (the next narrative call for the same task overwrites its own file, not yours).

## Indexing

This folder is registered in `.coding-os/rag-config.yaml` as `type: breakthrough` with `priority: 0.8`. `make docs-index` picks up new files automatically — they become searchable via `cos_doc_search(source_types="breakthrough")`.
