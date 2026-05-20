"""_absolute_module_for: relative-import resolution from a file's path."""

from __future__ import annotations

from graph_os.extractors.code_python import _absolute_module_for


def test_absolute_passthrough():
    assert _absolute_module_for("os.path", path="core/graph_os/types.py") == "os.path"


def test_empty_returns_empty():
    assert _absolute_module_for(None, path="core/graph_os/types.py") == ""
    assert _absolute_module_for("", path="core/graph_os/types.py") == ""


def test_single_dot_resolves_to_package():
    assert _absolute_module_for(".", path="core/graph_os/types.py") == "graph_os"


def test_double_dot_goes_up_one_level():
    result = _absolute_module_for("..types", path="core/graph_os/backends/sqlite_backend.py")
    assert result == "graph_os.types"


def test_triple_dot_goes_up_two_levels():
    result = _absolute_module_for("...types", path="core/graph_os/backends/foo/bar.py")
    assert result == "graph_os.types"


def test_relative_overshoot_falls_back_gracefully():
    result = _absolute_module_for("....foo", path="core/graph_os/types.py")
    assert result == "foo"


def test_dotted_relative_appends_tail():
    result = _absolute_module_for(
        "..extractors.code_python", path="core/graph_os/backends/sqlite_backend.py"
    )
    assert result == "graph_os.extractors.code_python"
