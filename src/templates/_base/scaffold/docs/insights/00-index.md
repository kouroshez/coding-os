<!-- domain:ALL | layer:index | ssot:true | updated:{{DATE}} -->
# Breakthroughs — Index

Purpose: Long-form write-ups of non-obvious fixes — a rework→success cycle told in full so future work can avoid the same dead-ends. The one-line lesson goes in `.agents/memory/`; its memory file links the write-up here.
Read when: Starting a task that touches an area with past breakthroughs, or onboarding to the project.
Skip when: The active task is routine and neither the memory index nor `cos_doc_search` points at a write-up.
Read next: The specific breakthrough file relevant to the area you're working on.

> Nav: [Docs Index](../00-index.md)

## How entries are created

Write them by hand, named `<TASK-ID>-<slug>.md`, with the doc header and the sections What Failed, What Worked and Key Insight.

## Indexing

This folder is registered in `.coding-os/rag-config.yaml` as `type: breakthrough` with `priority: 0.8`. `make docs-index` picks up new files automatically — they become searchable via `cos_doc_search(source_types="breakthrough")`.
