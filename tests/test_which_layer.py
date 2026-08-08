"""Tests for the meta-engineering which_layer.py classifier."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[1]
        / "src"
        / "templates"
        / "meta"
        / "skills"
        / "meta-engineering"
        / "scripts"
    ),
)

import which_layer as wl


def test_hooks_are_dna_live_symlink() -> None:
    layer, prop = wl.classify("src/core/hooks/foo.sh")
    assert "DNA" in layer and "symlink" in prop


def test_adapter_is_mrna() -> None:
    assert "mRNA" in wl.classify("src/adapters/claude/install.sh")[0]


def test_template_is_phenotype() -> None:
    assert "phenotype" in wl.classify("src/templates/nextjs/stack.yaml")[0]


def test_cli_is_factory() -> None:
    assert "factory" in wl.classify("src/cli/main.py")[0]


def test_most_specific_wins() -> None:
    # src/core/hooks/ must win over the generic src/core/ rule
    assert "symlink" in wl.classify("src/core/hooks/x.sh")[1]


def test_unknown_path() -> None:
    assert wl.classify("random/file.txt")[0] == "unknown"
