"""
Coding OS — doc-sync staleness scanner (graph- and FTS-aware).

PURPOSE
    PostToolUse Write|Edit|MultiEdit helper. Given the just-edited code
    file (and optionally the pre-edit content), surface docs that look
    out of sync with the new code.

WHY THIS BEAT THE NAIVE REGEX HOOK
    1. **Signature drift** — function name unchanged but parameter list
       grew/shrunk. The regex hook missed this; the user's birthdate
       example is exactly this case.
    2. **FTS-backed doc candidates** — instead of guessing docs from
       path heuristics, query the SQLite FTS5 index thinking_os already
       maintains over `docs/**/*.md`. Sub-10 ms per query, far more
       accurate than path-mirror.
    3. **Optional graph context** — when the graph_os backend is
       available, add a one-line "this symbol is referenced by N other
       files" hint via `cos_graph_references`. Capped at 200 ms so the
       hot path stays fast.

OUTPUT (one line per finding, tab-separated)
    STALE\t<doc_path>\t<reason>
Always exits 0 — this is a WARN signal, never a BLOCK.
"""

from __future__ import annotations

import re
import sqlite3
import sys
import time
from pathlib import Path

from _doc_sync_symbols import (
    CODE_EXT_TO_LANG as CODE_EXT_TO_LANG,
    DOC_EXTENSIONS as DOC_EXTENSIONS,
    _extract_symbols as _extract_symbols,
)

# ── Tunables ─────────────────────────────────────────────────────────────
_MAX_CANDIDATES = 6
_GRAPH_BUDGET_S = 0.2
_FTS_BUDGET_S = 0.1


def _find_project_root(code_file: Path) -> Path | None:
    p = code_file.resolve().parent
    while p != p.parent:
        if (p / ".coding-os").is_dir() or (p / "AGENTS.md").is_file():
            return p
        p = p.parent
    return None


def _doc_anchor_paths(project_root: Path) -> list[Path]:
    """Files the agent already declared as 'this code traces to'."""
    out: list[Path] = []
    state = project_root / ".coding-os"
    if not state.is_dir():
        return out
    for agent_dir in state.iterdir():
        anchor = agent_dir / ".doc-anchor"
        if anchor.is_file():
            try:
                rel = anchor.read_text(encoding="utf-8").strip()
                if rel:
                    p = (project_root / rel).resolve()
                    if p.is_file() and p.suffix in DOC_EXTENSIONS:
                        out.append(p)
            except OSError:
                continue
    return out


def _fts_candidates(
    project_root: Path,
    symbols: list[str],
    limit: int,
) -> list[Path]:
    """Use thinking_os document_chunks_fts to find docs that lexically
    mention any of the given symbols. ~10 ms total for ≤8 symbols."""
    db_path = project_root / ".coding-os" / "coding-os.db"
    if not db_path.is_file() or not symbols:
        return []
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=0.5)
    except sqlite3.Error:
        return []
    try:
        # FTS5 OR query — quote symbols to avoid syntax issues.
        # E.g.: `"register_user" OR "AuthService"`
        terms = " OR ".join(f'"{s}"' for s in symbols if s.replace("_", "").isalnum())
        if not terms:
            return []
        deadline = time.time() + _FTS_BUDGET_S
        rows = conn.execute(
            """
            SELECT DISTINCT dc.source_path
            FROM document_chunks_fts
            JOIN document_chunks dc ON dc.id = document_chunks_fts.rowid
            WHERE document_chunks_fts MATCH ?
              AND dc.source_type = 'doc'
            LIMIT ?
            """,
            (terms, limit),
        ).fetchall()
        if time.time() > deadline:
            # Soft budget — the row materialisation already happened, but
            # if we somehow blew past deadline, bail.
            return []
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()

    out: list[Path] = []
    for (path,) in rows:
        try:
            p = (project_root / path).resolve() if not Path(path).is_absolute() else Path(path)
            if p.is_file() and p.suffix in DOC_EXTENSIONS:
                out.append(p)
        except OSError:
            continue
    return out


def _fts_is_empty(project_root: Path) -> bool:
    """True when document_chunks_fts has zero rows — Rule 19 enforcement is
    effectively off until `make docs-index` populates it."""
    db_path = project_root / ".coding-os" / "coding-os.db"
    if not db_path.is_file():
        return False
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=0.5)
    except sqlite3.Error:
        return False
    try:
        row = conn.execute("SELECT COUNT(*) FROM document_chunks_fts").fetchone()
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()
    return bool(row) and row[0] == 0


def _path_mirror_candidates(project_root: Path, code_file: Path) -> list[Path]:
    """Last-resort heuristic: domain-typical doc paths. Used to catch the
    "no FTS index yet" / "doc anchor not set" startup case."""
    out: list[Path] = []
    seen: set[Path] = set()

    def _add(p: Path) -> None:
        if p not in seen and p.exists() and p.is_file() and p.suffix in DOC_EXTENSIONS:
            out.append(p)
            seen.add(p)

    try:
        rel = code_file.resolve().relative_to(project_root.resolve())
    except ValueError:
        return out
    parts = rel.parts
    docs_dir = project_root / "docs"
    if not docs_dir.is_dir():
        return out
    if parts and parts[0] == "backend":
        _add(docs_dir / "playbooks" / "backend-api.md")
        _add(docs_dir / "engineering" / "backend-rules.md")
    if parts and parts[0] == "frontend":
        _add(docs_dir / "playbooks" / "frontend-ui.md")
        _add(docs_dir / "engineering" / "frontend-rules.md")
    if parts and parts[0] == "core" and len(parts) >= 2:
        sub = parts[1]
        _add(docs_dir / "engineering" / f"{sub}.md")
        _add(docs_dir / "engineering" / f"{sub.replace('_', '-')}.md")
    return out


# ── Drift detection ──────────────────────────────────────────────────────


def _check_doc(
    doc_path: Path,
    new_syms: dict[str, tuple[int, str]],
    old_syms: dict[str, tuple[int, str]],
) -> str | None:
    """Return a short reason string if `doc_path` references a removed,
    renamed, or signature-changed symbol from this edit."""
    try:
        text = doc_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    findings: list[str] = []

    # Signal 1 — symbol REMOVED (was in old, gone in new), still in doc.
    removed = set(old_syms) - set(new_syms)
    for sym in sorted(removed):
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(sym)}(?![A-Za-z0-9_])", text):
            findings.append(f"removed `{sym}` still mentioned")
            if len(findings) >= 2:
                break

    # Signal 2 — SIGNATURE CHANGED on a kept symbol (the user's birthdate
    # example). param count differs → high-confidence drift.
    for sym, (new_count, _new_sig) in new_syms.items():
        if sym not in old_syms:
            continue
        old_count, _old_sig = old_syms[sym]
        if old_count == -1 or new_count == -1:
            continue  # class symbol — skip
        if old_count != new_count:
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(sym)}(?![A-Za-z0-9_])", text):
                findings.append(
                    f"`{sym}` signature changed ({old_count}→{new_count} params); "
                    f"verify doc still describes the right shape"
                )
                if len(findings) >= 2:
                    break

    if findings:
        return "; ".join(findings[:2])

    # Signal 3 — soft: doc mtime older than code AND mentions any current
    # symbol. Lower confidence; only fire if no stronger signal hit.
    return None  # handled in main() with mtime check


# ── Optional graph enrichment ────────────────────────────────────────────


def _graph_reference_hint(symbol: str, code_file: Path, deadline: float) -> str | None:
    """If graph_os backend is up, add 'symbol is called from N other files'.
    Best-effort; silent on any failure."""
    if time.time() > deadline:
        return None
    try:
        # Lazy import — adds 30 ms but only when we already decided to WARN.
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        from graph_os.tools import graph as gtools  # type: ignore

        # cos_graph_references signature varies per version; call defensively.
        backend = gtools._backend()
        if backend is None:
            return None
        # Match by symbol name + any callsite outside the changed file.
        envelope = gtools.cos_graph_references(symbol)
        if not isinstance(envelope, dict) or not envelope.get("ok"):
            return None
        items = envelope.get("data", {}).get("references", [])
        external = [
            it
            for it in items
            if str(it.get("file") or it.get("path") or "")
            not in (str(code_file), str(code_file.name))
        ]
        n = len(external)
        if n == 0:
            return None
        return f"referenced from {n} other location(s)"
    except Exception:
        return None


# ── Main ─────────────────────────────────────────────────────────────────


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        return 0
    code_file = Path(argv[1])
    if not code_file.exists() or code_file.is_dir():
        return 0
    if code_file.suffix not in CODE_EXT_TO_LANG:
        return 0
    lang = CODE_EXT_TO_LANG[code_file.suffix]

    project_root = _find_project_root(code_file)
    if project_root is None:
        return 0

    try:
        new_text = code_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    new_syms = _extract_symbols(new_text, lang)

    old_text = argv[2] if len(argv) >= 3 else None
    old_syms = _extract_symbols(old_text, lang) if old_text else {}

    # If we have no diff context AND no public symbols, nothing to check.
    if not new_syms and not old_syms:
        return 0

    # Build candidate doc set (anchor → FTS hits → path mirror, capped).
    candidates: list[Path] = list(_doc_anchor_paths(project_root))
    seen: set[Path] = set(candidates)

    # One-shot warning when FTS is empty — Rule 19 enforcement can't fire
    # without it. Touched marker lives in state dir so we don't spam every Edit.
    if _fts_is_empty(project_root):
        marker = project_root / ".coding-os" / ".warn-fts-empty-shown"
        if not marker.exists():
            print(
                "INFO\t-\tdoc-sync inactive — document_chunks_fts is empty; "
                "run `make docs-index` to enable staleness detection"
            )
            try:
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.touch()
            except OSError as exc:
                sys.stderr.write(f"doc_sync_check: marker write skipped: {exc}\n")

    fts_query_syms = list(set(new_syms) | set(old_syms))[:8]
    for p in _fts_candidates(project_root, fts_query_syms, _MAX_CANDIDATES):
        if p not in seen:
            candidates.append(p)
            seen.add(p)
    if len(candidates) < 3:
        for p in _path_mirror_candidates(project_root, code_file):
            if p not in seen:
                candidates.append(p)
                seen.add(p)
    candidates = candidates[:_MAX_CANDIDATES]

    if not candidates:
        return 0

    findings: list[tuple[Path, str]] = []
    code_mtime = code_file.stat().st_mtime
    for doc in candidates:
        reason = _check_doc(doc, new_syms, old_syms)
        if reason:
            findings.append((doc, reason))
            continue
        # Soft signal: doc mtime older than code AND mentions any current
        # public symbol. Only when we have a real diff (old_text given).
        if old_text is not None:
            try:
                doc_mtime = doc.stat().st_mtime
            except OSError:
                continue
            if doc_mtime < code_mtime - 1:
                try:
                    text = doc.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                touched = [
                    s
                    for s in new_syms
                    if re.search(rf"(?<![A-Za-z0-9_]){re.escape(s)}(?![A-Za-z0-9_])", text)
                ]
                if touched:
                    findings.append(
                        (
                            doc,
                            f"older than code; mentions `{touched[0]}`"
                            f"{'…' if len(touched) > 1 else ''}",
                        )
                    )

    if not findings:
        return 0

    # Optional graph enrichment — only when we already decided to WARN.
    # First touched/kept symbol from the strongest signal.
    enrichment = None
    enrich_deadline = time.time() + _GRAPH_BUDGET_S
    for sym in (set(old_syms) - set(new_syms)) | (set(new_syms) & set(old_syms)):
        hint = _graph_reference_hint(sym, code_file, enrich_deadline)
        if hint:
            enrichment = f"`{sym}` {hint}"
            break

    try:
        code_file.resolve().relative_to(project_root.resolve())
    except ValueError:
        pass
    for doc, reason in findings[:3]:
        try:
            rel_doc = doc.resolve().relative_to(project_root.resolve())
        except ValueError:
            rel_doc = doc
        print(f"STALE\t{rel_doc}\t{reason}")
    if enrichment:
        print(f"INFO\t-\t{enrichment}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
