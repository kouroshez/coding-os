"""Smoke test for cos_doc_header + cos_doc_headers_by (TASK-155)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make tools/ importable the same way server.py does it.
THINKING_OS = Path(__file__).resolve().parent.parent / "core" / "thinking_os"
sys.path.insert(0, str(THINKING_OS))

from tools.docs import list_doc_headers, parse_doc_header  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GOVERNANCE = ROOT / "docs" / "governance"


def _check(condition: bool, message: str) -> None:
    print(("OK  : " if condition else "FAIL: ") + message)
    if not condition:
        sys.exit(1)


def main() -> None:
    # Single-doc parse.
    target = GOVERNANCE / "critical-rules.md"
    header = parse_doc_header(target)
    _check(header is not None, f"parse_doc_header returns dict for {target.name}")
    fm = header["frontmatter"]
    ob = header["opening_block"]
    _check(fm.get("domain") == "DOCS", f"frontmatter domain == DOCS (got {fm.get('domain')!r})")
    _check(fm.get("layer") == "policy", f"frontmatter layer == policy (got {fm.get('layer')!r})")
    _check(bool(ob.get("purpose")), "opening_block.purpose populated")
    _check(bool(ob.get("read_when")), "opening_block.read_when populated")
    _check(bool(ob.get("read_next")), "opening_block.read_next populated")
    _check(header["header_token_estimate"] < 300,
           f"header_token_estimate < 300 (got {header['header_token_estimate']})")

    # Bulk scan with filter.
    rows = list_doc_headers(GOVERNANCE, domain="DOCS", limit=20)
    _check(len(rows) >= 3, f"list_doc_headers found ≥3 DOCS rows (got {len(rows)})")
    titles = [r["title"] for r in rows]
    _check("Critical Rules — Full Text" in titles,
           f"Critical Rules surfaced (titles={titles[:3]}…)")

    # Filter by layer.
    policies = list_doc_headers(GOVERNANCE, domain="DOCS", layer="policy", limit=20)
    _check(len(policies) >= 1,
           f"list_doc_headers(domain=DOCS, layer=policy) ≥1 (got {len(policies)})")

    # Negative — non-existent layer.
    none = list_doc_headers(GOVERNANCE, domain="DOCS", layer="not-a-layer")
    _check(none == [], "filter on bogus layer returns empty list")

    # Compact JSON dump for visual inspection.
    print("\nSample header:")
    print(json.dumps({k: header[k] for k in ("title", "frontmatter", "opening_block")},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
