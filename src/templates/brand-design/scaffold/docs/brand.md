<!-- domain:PRODUCT | layer:spec | ssot:true | updated:{{DATE}} -->
# Brand — {{PROJECT_NAME}}

Purpose: Single source of truth for the brand: identity, visual system, production rules, platform image specs, the design-file map and asset naming.
Read when: Any design, image-generation, export or channel-setup task.
Skip when: The task only touches coding-os process docs.
Read next: [PRD snapshot](./prd/01-snapshot-vision.md), [Roadmap](./_meta/roadmap.md)

> Nav: [Docs Index](./00-index.md)

Each fact lives here once. Other docs, tasks and the design file link to a section; they never copy its values. An open decision goes to [questions](./_meta/questions.md) and is linked from its row.

## 1. Identity

| Item | Value |
|---|---|
| Name and handle | TBD: the public name, and the handle used on every platform |
| Wordmark | TBD |
| Channels | TBD: one link per platform page |
| Audience | TBD: who, where, and the language all brand text is written in |
| Topics | TBD: what the channels cover |

## 2. Visual system

Not decided yet. Once a direction is approved, its palette (hex and role), typefaces and logo rules are written here. The design file's colour variables and text styles are built from this section and never edited on their own.

## 3. Production rules

- Raster art (photos, illustrations, backdrops) comes from image generation into `assets/generated/`. Text, the wordmark and the logo are vector, built in the design file.
- Reference photos come only from `assets/reference/`.
- Third-party logos and key art stay out unless their licence allows it; their names appear as plain text.
- One master per deliverable: a design reused across platforms is one frame, exported at each platform's size.
- Every export meets the strictest file-size limit among the platforms in § 4 that use it.

## 4. Platform image specs

Checked TBD against each platform's help pages. One row per exported asset; re-check a row before its next export.

| Platform | Asset | Size (px) | Rule |
|---|---|---|---|
| TBD | TBD | TBD | Safe area, file-size limit, format |

Sources: TBD, one link per platform help page.

## 5. Design file

- File: TBD, with its link and file key. It holds designs only, never documentation.
- Pages: TBD, for example `Cover` · `Foundations` · `Assets` · `Components` · one page per deliverable type · `Proposals` · `Archive`.
- Frame name: `<Platform> · <Asset> · <W×H>`. The export file is its slug, e.g. `<platform>-<asset>-<w>x<h>.png`.
- A replaced design moves to `Archive` with its date and reason before anything is deleted.

## 6. Asset folders

| Folder | Holds | In git |
|---|---|---|
| `assets/reference/` | Photos and style references the owner supplies | No (its own `.gitignore`) |
| `assets/generated/` | Raw image-generation output, named `<yyyy-mm-dd>-<subject>-<n>.png` | No (its own `.gitignore`) |
| `assets/export/` | Final upload files, named from their design-file frame | Yes |
