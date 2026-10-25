"""`x.method()` resolves through x's annotation or constructor, not to a variable-named stub."""

from __future__ import annotations

from graph_os.extractors import code_python

SOURCE = """
from app.backend import GraphBackend


class Local:
    def run(self):
        return 1


def use(backend: GraphBackend, maybe: "Local | None" = None, opt: GraphBackend | None = None):
    backend.get_node("x")
    opt.list_edges()
    local = Local()
    local.run()
    maybe.run()


def conflicting():
    thing = Alpha()
    thing = Beta()
    thing.go()
"""


def _call_targets() -> set[str]:
    result = code_python.extract("app/views.py", SOURCE)
    return {edge.target_uid for edge in result.edges if edge.edge_type == "calls"}


def test_an_annotated_parameter_resolves_to_the_imported_class_method():
    targets = _call_targets()
    assert "code:external:app.backend.GraphBackend:get_node" in targets
    assert "code:external:app.backend.GraphBackend:list_edges" in targets  # `X | None`
    assert "code:external:unresolved:backend.get_node" not in targets


def test_a_local_class_instance_resolves_to_its_method():
    targets = _call_targets()
    assert "code:method:app/views.py::Local.run" in targets
    assert "code:external:unresolved:local.run" not in targets


def test_a_name_bound_to_two_classes_stays_unresolved():
    assert "code:external:unresolved:thing.go" in _call_targets()


def test_typed_calls_are_strong_not_certain():
    result = code_python.extract("app/views.py", SOURCE)
    edge = next(e for e in result.edges if e.target_uid.endswith("GraphBackend:get_node"))
    assert edge.confidence == 0.8
