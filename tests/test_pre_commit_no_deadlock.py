"""Regression: pre-commit must not deadlock on a large staged set.

Root cause (debugger): `.git/hooks/pre-commit` built its FILE_ARGS array with
`done <<< "$STAGED_FILES"`. A `<<<` here-string writes the whole list to a
self-pipe before the `read` loop drains it; once the (shared-index) staged set
exceeds the pipe buffer the write() blocks forever — the bash 5.x heredoc
deadlock the hook's own header warns about (Rule 8). Fixed by feeding the loop
via process substitution (`done < <(printf '%s\\n' "$STAGED_FILES")`), which is
drained line-by-line and never buffers the whole list.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src" / "scripts" / "_pre_commit_body.sh"


def test_source_has_no_heredoc_redirect() -> None:
    body = _SRC.read_text(encoding="utf-8")
    assert 'done <<< "$STAGED_FILES"' not in body, "reverted to the deadlocking here-string"
    assert "done < <(printf" in body, "process-substitution drain form missing"


def test_array_build_does_not_deadlock_on_large_list() -> None:
    # 5000 paths (~300 KB) — far above any pipe buffer. The old `<<<` form
    # deadlocks here; the process-substitution form completes line-by-line.
    # Fed via stdin, not argv: Linux MAX_ARG_STRLEN caps a single argv element
    # at 128 KiB (execve fails with E2BIG), and the real hook holds the list
    # in a command-substitution variable anyway.
    n = 5000
    staged = "\n".join(f"src/core/hooks/file_{i}.sh" for i in range(n))
    script = (
        'STAGED_FILES="$(cat)"\n'
        "FILE_ARGS=()\n"
        "while IFS= read -r FILE; do\n"
        '  [[ -z "$FILE" ]] && continue\n'
        '  FILE_ARGS+=("$FILE")\n'
        "done < <(printf '%s\\n' \"$STAGED_FILES\")\n"
        'echo "${#FILE_ARGS[@]}"\n'
    )
    proc = subprocess.run(
        ["bash", "-c", script],
        input=staged,
        capture_output=True,
        text=True,
        timeout=20,  # a deadlock would blow this; the fix returns in <1s
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == str(n)


def test_no_done_heredoc_readloop_anywhere() -> None:
    """Repo-wide guard against the deadlock-prone `done <<< "$VAR"` form.

    The pattern recurred in 4 sites (pre-commit + auto-reindex-shell-ops +
    enforce-doc-sync + enforce-verify); all converted to process substitution.
    A `while … done <<< "$VAR"` blocks forever once $VAR exceeds the pipe
    buffer (bash 5.x heredoc deadlock). Single `read`/`awk <<<` on small,
    bounded values is fine — only the loop-feeding form is banned here.
    """
    import re

    repo = _SRC.parents[2]  # src/scripts/_pre_commit_body.sh -> src/scripts -> src -> repo root
    roots = [
        repo / "src" / "core" / "hooks",
        repo / "src" / "core" / "scripts",
        repo / "src" / "scripts",
    ]
    pat = re.compile(r"done\s*<<<")
    offenders: list[str] = []
    for root in roots:
        if not root.is_dir():
            continue
        for sh in root.glob("*.sh"):
            for i, line in enumerate(
                sh.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
            ):
                if pat.search(line):
                    offenders.append(f"{sh.relative_to(repo)}:{i}: {line.strip()}")
    assert not offenders, "deadlock-prone `done <<<` read-loop(s):\n" + "\n".join(offenders)
