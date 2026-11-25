<!-- domain:DOCS | layer:asset | ssot:false | updated:2026-06-04 -->
# Doc Ship Checklist

Run before committing any doc. Every box, or it doesn't ship.

## Structure
- [ ] Header present + correct: `<!-- domain | layer | ssot | updated:YYYY-MM-DD -->`.
- [ ] `Purpose / Read when / Skip when / Read next` (or `> P/R/S/N`) block present.
- [ ] `> Nav:` block links the section index + docs index.
- [ ] Point is in the first paragraph (newspaper structure).
- [ ] Each heading is one idea; headings alone tell the story.
- [ ] Layer matches content (no reference tables in a playbook, no hand-waving in a spec).

## Prose
- [ ] Active voice, present tense, named subject.
- [ ] Every "fast/slow/large" replaced with a number.
- [ ] Every vague noun replaced with a path or symbol.
- [ ] Hedges/intensifiers cut or justified.
- [ ] Every rule shown bad→good where code is involved.
- [ ] Every code claim verified against the code, not memory.

## Hygiene
- [ ] No content duplicated from another doc — linked instead.
- [ ] New doc justified (existing doc had wrong scope) — else a section was added.
- [ ] `python3 scripts/new_doc.py` header shape matched (if scaffolded).

## Verify
- [ ] `make docs-index-regen` lists it in the right `00-index.md`.
- [ ] `make docs-lint` clean for this file.
