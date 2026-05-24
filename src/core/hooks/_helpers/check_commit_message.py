import re
import sys
from pathlib import Path

MAX_TITLE_CHARS = 100
MAX_BODY_LINES = 3
MAX_PERSIAN_QUOTED_CHARS = 40

ATTRIBUTION_PATTERNS = [
    re.compile(r"^Co-Authored-By:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"\U0001F916"),
    re.compile(r"Generated with \[?Claude", re.IGNORECASE),
    re.compile(r"noreply@anthropic\.com", re.IGNORECASE),
    re.compile(r"claude\.com/claude-code", re.IGNORECASE),
    re.compile(r"@anthropic\.com", re.IGNORECASE),
]

USER_PROMPT_RE = re.compile(r"^USER\b", re.IGNORECASE | re.MULTILINE)


def check_message(text: str) -> list[str]:
    errors: list[str] = []
    raw_lines = text.split("\n")
    lines = [l for l in raw_lines if not l.startswith("#")]
    title_idx = next((i for i, l in enumerate(lines) if l.strip()), None)
    if title_idx is None:
        return ["commit message is empty"]
    title = lines[title_idx].rstrip()
    body_lines = lines[title_idx + 1 :]
    text_clean = "\n".join(lines)

    if len(title) > MAX_TITLE_CHARS:
        errors.append(f"title is {len(title)} chars; max {MAX_TITLE_CHARS}")

    body_nonempty = [l for l in body_lines if l.strip()]
    if len(body_nonempty) > MAX_BODY_LINES:
        errors.append(f"body has {len(body_nonempty)} non-empty lines; max {MAX_BODY_LINES}")

    for pat in ATTRIBUTION_PATTERNS:
        m = pat.search(text_clean)
        if m:
            errors.append(f"forbidden attribution: {m.group(0)!r}")
            break

    if USER_PROMPT_RE.search(text_clean):
        errors.append("forbidden line starting with USER/User/user (prompt leak)")

    for m in re.finditer(r'"([^"]+)"', text_clean):
        chunk = m.group(1)
        persian = sum(1 for c in chunk if "؀" <= c <= "ۿ")
        if persian > MAX_PERSIAN_QUOTED_CHARS:
            errors.append(
                f"forbidden quoted Persian/Arabic text ({persian} chars) — prompt leak"
            )
            break

    return errors


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] == "-":
        text = sys.stdin.read()
    else:
        text = Path(sys.argv[1]).read_text(encoding="utf-8")
    errors = check_message(text)
    if errors:
        print("ERROR commit-message:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print(
            "\nContract: title ≤100 chars · body ≤3 non-empty lines · "
            "no attribution / USER prompts / Persian quotes.",
            file=sys.stderr,
        )
        print("Spec: src/core/rules/git-workflow.md § Commit Message Contract", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
