"""Rewrite each agent .md SSOT to be dual-mode (composer JSON + interactive prose).

Reads every src/core/thinking_os/agents/<role>.md (excluding README), locates
the ``## Inputs you receive`` and ``## Output contract`` sections, replaces
them with the dual-mode templates while preserving the existing JSON skeleton
verbatim. Idempotent: re-running on an already-converted file is a no-op.

Run:
    python src/scripts/refactor_agent_dual_mode.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

AGENTS_DIR = Path(__file__).resolve().parent.parent / "core" / "thinking_os" / "agents"

SENTINEL = "This command runs in **two modes**"

INPUT_BLOCK_RE = re.compile(
    r"^## Inputs you receive\n+```json\n\{\{ ([A-Za-z]+Input) \}\}\n```\n",
    re.MULTILINE,
)
OUTPUT_HEADING_RE = re.compile(
    r"^## Output contract\nReturn JSON matching `([A-Za-z]+Output)`\. No prose outside the JSON block\.\n+```json\n",
    re.MULTILINE,
)


def render_inputs(input_name: str) -> str:
    return f"""## Inputs you receive

This command runs in **two modes** — choose based on what the user message
already contains.

**(A) Composer mode** — `cos_dispatch_formula_run` invoked this role. The user
message contains a `{input_name}` JSON object (shape defined by the
`input_schema` frontmatter field).

**(B) Interactive mode** — user invoked the slash command and the user
message has **no `{input_name}`-shaped JSON**. Auto-detect every field from
repo state before starting the procedure:

| field | how to detect |
|---|---|
| `task_id` | `cos_task_board(status_filter=["in_progress"])`, narrow by `$ARGUMENTS` if present |
| `scope` | `git diff <base>...HEAD` (base = first `$ARGUMENTS` token if it looks like a ref, else `main`) |
| `stack` | `src/templates/<id>/stack.yaml` of the enabled template |
| `domain` | `cos_doc_headers_by(domain=...)` or the active task's frontmatter |
| `nfr_targets` | `docs/_meta/nfr.yaml` if present, else `"none configured"` |

Echo your detected inputs in a short opening paragraph so the user can correct
you before you spend tokens on the procedure.

"""


def render_output_prefix(output_name: str) -> str:
    return f"""## Output contract

**Match the invocation mode**:

**(A) Composer mode** — return JSON only matching `{output_name}`. No prose
outside the fenced block:

```json
"""


def render_output_suffix(output_name: str) -> str:
    return f"""
**(B) Interactive mode** — return a Markdown review with these sections:

1. **Detected inputs** — one paragraph echoing task_id / scope / stack / nfr.
2. **Summary** — one paragraph: what was done, overall verdict.
3. **Findings or Deliverables** — bulleted; severities critical / high / medium / low / info where applicable.
4. **Next step** — single recommended action (or "ready to hand off to <next-role>").

Then append the **same `{output_name}` envelope** as a fenced ```json``` block
at the very bottom so `cos_supervise_record_output` can parse it. Both
audiences (human + composer) consume the same output from one emission.
"""


def transform(text: str) -> tuple[str, str | None]:
    if SENTINEL in text:
        return text, None

    m_in = INPUT_BLOCK_RE.search(text)
    m_out = OUTPUT_HEADING_RE.search(text)
    if not m_in or not m_out:
        return text, None

    input_name = m_in.group(1)
    output_name = m_out.group(1)

    new_text = text[: m_in.start()] + render_inputs(input_name) + text[m_in.end() :]

    m_out2 = OUTPUT_HEADING_RE.search(new_text)
    if not m_out2:
        return text, None

    skeleton_start = m_out2.end()
    close_idx = new_text.find("\n```", skeleton_start)
    if close_idx == -1:
        return text, None
    close_end = close_idx + len("\n```")

    new_text = (
        new_text[: m_out2.start()]
        + render_output_prefix(output_name)
        + new_text[skeleton_start:close_end]
        + render_output_suffix(output_name)
        + new_text[close_end:]
    )
    return new_text, input_name.removesuffix("Input").lower()


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--root",
        type=Path,
        default=AGENTS_DIR,
        help="Agents dir (default: src/core/thinking_os/agents).",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report what would change without writing."
    )
    args = parser.parse_args(argv)

    rewrote: list[str] = []
    skipped: list[str] = []
    errors = 0
    for md in sorted(args.root.glob("*.md")):
        if md.name == "README.md":
            continue
        try:
            original = md.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"ERROR reading {md.name}: {exc}", file=sys.stderr)
            errors += 1
            continue
        new_text, role = transform(original)
        if role is None:
            skipped.append(md.name)
            continue
        if args.dry_run:
            rewrote.append(f"{md.name} (dry-run)")
            continue
        try:
            md.write_text(new_text, encoding="utf-8")
        except OSError as exc:
            print(f"ERROR writing {md.name}: {exc}", file=sys.stderr)
            errors += 1
            continue
        rewrote.append(md.name)
    print(f"rewrote {len(rewrote)}: {', '.join(rewrote) or '(none)'}")
    print(f"skipped {len(skipped)}: {', '.join(skipped) or '(none)'}")
    if errors:
        print(f"errors: {errors}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
