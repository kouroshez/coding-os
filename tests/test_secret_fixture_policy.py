"""Guard the secret-fixture policy in SECURITY.md § Test fixtures for secret detection.

This repository ships a secret detector, so it must keep credential-shaped test
data around. The policy is that such fixtures are safe *by construction* —
composed at run time, deliberately sub-threshold, or a vendor-published reserved
example — never a realistic full-length literal. This test is the enforcement:
it fails if any tracked file gains a string that a real vendor scanner would
match, so the rule survives without depending on a reviewer noticing.

The patterns below cannot match themselves: every one has a regex metacharacter
immediately after its literal prefix, which the following character class
excludes.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

# Full-length vendor formats — the shapes a real scanner alerts on.
VENDOR_PATTERNS = {
    "aws-access-key": re.compile(r"(?:AKIA|ASIA)[0-9A-Z]{16}"),
    "github-token": re.compile(r"gh[pousr]_[A-Za-z0-9]{36}"),
    "github-pat-fine-grained": re.compile(r"github_pat_[A-Za-z0-9_]{80,}"),
    "stripe-live-key": re.compile(r"[sr]k_live_[A-Za-z0-9]{24,}"),
    "slack-token": re.compile(r"xox[abprs]-[A-Za-z0-9-]{20,}"),
    "google-api-key": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "openai-project-key": re.compile(r"sk-proj-[A-Za-z0-9_\-]{40,}"),
    "openai-legacy-key": re.compile(r"sk-[A-Za-z0-9]{40,}"),
    "anthropic-key": re.compile(r"sk-ant-(?:api|admin)[0-9]{2}-[A-Za-z0-9_\-]{80,}"),
    "npm-token": re.compile(r"npm_[A-Za-z0-9]{36}"),
    # A bare BEGIN header is itself a legitimate fixture (block-secrets.sh is
    # tested with one); only a header followed by base64 key material is a key.
    "private-key-material": re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----\s*\n[A-Za-z0-9+/=]{40,}"
    ),
}

# Vendor-reserved identifiers that can never authenticate. Composed rather than
# written literally, so this guard does not itself trip the guards it documents.
VENDOR_RESERVED = frozenset(
    {
        "AKIA" + "IOSFODNN7EXAMPLE",
        "ASIA" + "IOSFODNN7EXAMPLE",
    }
)

# Binary and vendored trees carry no hand-authored fixtures worth policing.
SKIP_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".woff2"})
SKIP_PREFIXES = ("node_modules/", ".venv/")


def _tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout
    paths = []
    for rel in out.split("\0"):
        if not rel or rel.startswith(SKIP_PREFIXES) or Path(rel).suffix in SKIP_SUFFIXES:
            continue
        paths.append(rel)
    return [Path(p) for p in paths]


def _violations() -> list[tuple[str, str, str]]:
    found: list[tuple[str, str, str]] = []
    for rel in _tracked_files():
        try:
            text = (REPO / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for name, pattern in VENDOR_PATTERNS.items():
            for match in pattern.finditer(text):
                if match.group(0) in VENDOR_RESERVED:
                    continue
                line = text[: match.start()].count("\n") + 1
                found.append((f"{rel}:{line}", name, match.group(0)[:24] + "…"))
    return found


def test_no_scannable_credential_literals() -> None:
    violations = _violations()
    assert not violations, (
        "Tracked files contain credential-shaped literals at full vendor length.\n"
        + "\n".join(f"  {loc}  [{kind}]  {sample}" for loc, kind, sample in violations)
        + "\n\nA fixture must be safe by construction — compose it at run time, keep the"
        "\nbody sub-threshold, or use a vendor-published reserved example."
        "\nSee SECURITY.md § Test fixtures for secret detection."
    )


def test_scanner_exclusions_are_declared_and_narrow() -> None:
    config = REPO / ".github" / "secret_scanning.yml"
    assert config.exists(), (
        "The fixture paths must be declared to GitHub in-repo so the reasoning is "
        "public and reviewable, not buried in an alert dismissal."
    )
    listed = [
        line.split("#", 1)[0].strip().lstrip("-").strip().strip('"').strip("'")
        for line in config.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("- ")
    ]
    assert listed, "secret_scanning.yml declares no paths-ignore entries"
    for entry in listed:
        assert not entry.rstrip("/*") in {"src", "tests", "docs", ""}, (
            f"paths-ignore entry {entry!r} suppresses scanning for a whole hand-authored "
            "tree; keep the list to detector fixtures and generated snapshots."
        )


@pytest.mark.parametrize(
    "path",
    [
        "tests/test_block_secrets.py",
        "src/core/thinking_os/tests/test_sanitizer.py",
    ],
)
def test_declared_fixture_files_still_exist(path: str) -> None:
    # A stale paths-ignore entry silently widens the unscanned surface.
    assert (REPO / path).exists(), f"{path} is declared in secret_scanning.yml but is gone"
