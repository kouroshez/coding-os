<!-- domain:ARCH | layer:index | ssot:true | updated:2026-06-05 -->

# Architecture Decision Records

This directory holds the canonical record of major architectural
decisions made on coding-os. Each ADR documents:

- **Context** — why the decision had to be made.
- **Decision** — what was chosen.
- **Consequences** — what the choice costs us in exchange.
- **Alternatives** — what else we considered + why we passed.

Format follows Michael Nygard's classic short style. ADRs are
immutable once accepted — supersede via a new ADR rather than
edit. Status values: `Proposed`, `Accepted`, `Deprecated`,
`Superseded by ADR-NNNN`.

## Index

| #    | Title                                                                     | Status   |
| ---- | ------------------------------------------------------------------------- | -------- |
| 0001 | [Adopt Python src-layout](./0001-src-layout.md)                           | Accepted |
| 0002 | [Retire the Kuzu graph backend](./0002-retire-kuzu-backend.md)            | Accepted |
| 0003 | [Intent-enforcement layer](./0003-intent-enforcement-layer.md)            | Accepted |
| 0004 | [Web Hub singleton](./0004-web-hub-singleton.md)                          | Accepted |
| 0005 | [board_os file-first Scrumban](./0005-board-os-file-first-scrumban.md)    | Accepted |

## Adding a new ADR

1. Take the next number (`ls docs/architecture/adr/ | sort | tail -1`).
2. `cp docs/architecture/adr/_template.md docs/architecture/adr/NNNN-short-slug.md` (or copy
   an existing ADR — there is no rigid template).
3. Write under Context → Decision → Consequences → Alternatives.
4. Set Status to `Proposed`; flip to `Accepted` when merged.
5. Add a row to the index above.

## When to write one

Write an ADR when:

- The decision is hard to reverse (database choice, package layout,
  protocol).
- A future contributor would reasonably ask "why this and not the
  obvious alternative?".
- The decision spans multiple subsystems (changing one would
  require changing others).

Do NOT write an ADR for:

- Routine implementation choices (which Python library to use for X
  when several are equivalent).
- Bug fixes — the commit message is the record.
- Style preferences — `clean-code` skill + ruff config is the record.
