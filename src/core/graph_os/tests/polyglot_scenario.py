"""Scenario type shared by the polyglot corpus modules."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

pytest.importorskip("tree_sitter")


_FUNC_KINDS = {"code:function", "code:method"}
_CLASS_KINDS = {"code:class", "code:interface", "code:trait", "code:struct", "code:enum"}
_DECOY_NAMES = {"decoy", "fake_fn", "FakeClass", "phantom"}


@dataclass
class Scenario:
    name: str
    file: str
    src: str
    funcs: set[str]
    classes: set[str] = field(default_factory=set)
    edges: list[tuple[str, str, str]] = field(default_factory=list)  # (type, src_frag, tgt_frag)
    has_decoys: bool = False
