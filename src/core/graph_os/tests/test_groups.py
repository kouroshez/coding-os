"""Tests for the I.12 repo-groups subsystem."""

from __future__ import annotations

import pytest

from graph_os.groups import (
    ConflictError,
    GroupManifest,
    GroupMember,
    infer_cross_repo_edges,
    load_manifest,
    register_member,
    save_manifest,
)
from graph_os.groups.cross_repo import MemberInputs


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


class TestManifest:
    def test_round_trip(self, tmp_path):
        m = GroupManifest(
            name="my-platform",
            members=[
                GroupMember(
                    alias="backend",
                    path="/repos/backend",
                    owned_routes=["/api/users", "/api/users/*"],
                )
            ],
        )
        path = tmp_path / "group.json"
        save_manifest(m, path)
        loaded = load_manifest(path)
        assert loaded.name == "my-platform"
        assert len(loaded.members) == 1
        assert loaded.members[0].owned_routes == ["/api/users", "/api/users/*"]

    def test_register_member_idempotent(self):
        base = GroupManifest(name="g", members=[])
        added = register_member(base, alias="be", path="/be", owned_routes=["/x"])
        again = register_member(added, alias="be", path="/be", owned_routes=["/x", "/y"])
        assert len(again.members) == 1
        assert "/y" in again.members[0].owned_routes

    def test_conflicting_ownership_raises(self):
        base = GroupManifest(name="g", members=[])
        m1 = register_member(base, alias="a", path="/a", owned_routes=["/api/users"])
        with pytest.raises(ConflictError):
            register_member(m1, alias="b", path="/b", owned_routes=["/api/users"])

    def test_wildcard_owns(self):
        m = GroupMember(alias="a", path="/a", owned_routes=["/api/*"])
        assert m.owns_route("/api/x") is True
        assert m.owns_route("/api/x/y") is False
        m2 = GroupMember(alias="b", path="/b", owned_routes=["/internal/**"])
        assert m2.owns_route("/internal/deep/path") is True


# ---------------------------------------------------------------------------
# Cross-repo inference
# ---------------------------------------------------------------------------


class TestCrossRepo:
    def _manifest(self, *, owns_a=None, owns_b=None):
        base = GroupManifest(name="plat", members=[])
        m = register_member(
            base, alias="backend-a", path="/a", owned_routes=list(owns_a or [])
        )
        return register_member(
            m, alias="backend-b", path="/b", owned_routes=list(owns_b or [])
        )

    def _inputs(self, *, a_routes=(), b_routes=(), front_fetches=()):
        return [
            MemberInputs(alias="backend-a", routes=list(a_routes)),
            MemberInputs(alias="backend-b", routes=list(b_routes)),
            MemberInputs(alias="frontend", fetches=list(front_fetches)),
        ]

    def test_ownership_declared_yields_095(self):
        manifest = self._manifest(owns_a=["/api/users"])
        inputs = self._inputs(
            a_routes=[{"method": "get", "path": "/api/users", "handler_uid": "cos:route:GET:/api/users"}],
            b_routes=[{"method": "get", "path": "/api/users", "handler_uid": "cos:route:GET:/api/users"}],
            front_fetches=[
                {
                    "caller_uid": "code:function:front::listUsers",
                    "method": "get",
                    "path": "/api/users",
                }
            ],
        )
        report = infer_cross_repo_edges(manifest, inputs)
        assert len(report.edges) == 1
        assert report.edges[0].confidence == pytest.approx(0.95)

    def test_no_ownership_yields_06_per_candidate(self):
        manifest = self._manifest()
        inputs = self._inputs(
            a_routes=[{"method": "get", "path": "/api/users", "handler_uid": "cos:route:GET:a"}],
            b_routes=[{"method": "get", "path": "/api/users", "handler_uid": "cos:route:GET:b"}],
            front_fetches=[
                {"caller_uid": "code:function:front::x", "method": "get", "path": "/api/users"}
            ],
        )
        report = infer_cross_repo_edges(manifest, inputs)
        assert len(report.edges) == 2
        assert all(e.confidence == pytest.approx(0.6) for e in report.edges)
        assert "/api/users" in report.ambiguous_routes

    def test_unresolved_fetch_recorded(self):
        manifest = self._manifest()
        inputs = self._inputs(
            front_fetches=[
                {"caller_uid": "c", "method": "get", "path": "/api/ghost"}
            ],
        )
        report = infer_cross_repo_edges(manifest, inputs)
        assert "/api/ghost" in report.unresolved_fetches
        assert report.edges == []

    def test_self_fetch_skipped(self):
        manifest = self._manifest(owns_a=[])
        inputs = [
            MemberInputs(
                alias="backend-a",
                routes=[{"method": "get", "path": "/x", "handler_uid": "cos:route:a"}],
                fetches=[{"caller_uid": "c", "method": "get", "path": "/x"}],
            )
        ]
        report = infer_cross_repo_edges(manifest, inputs)
        assert report.edges == []

    def test_evidence_includes_route_match(self):
        manifest = self._manifest(owns_a=["/api/users"])
        inputs = self._inputs(
            a_routes=[{"method": "get", "path": "/api/users"}],
            front_fetches=[
                {"caller_uid": "c", "method": "get", "path": "/api/users"}
            ],
        )
        report = infer_cross_repo_edges(manifest, inputs)
        signals = {s.signal_name for s in report.edges[0].evidence}
        assert "ownership_declared" in signals

    def test_ambiguous_list_accumulates_one_per_candidate(self):
        manifest = self._manifest()
        inputs = self._inputs(
            a_routes=[{"method": "get", "path": "/x"}],
            b_routes=[{"method": "get", "path": "/x"}],
            front_fetches=[{"caller_uid": "c", "method": "get", "path": "/x"}],
        )
        report = infer_cross_repo_edges(manifest, inputs)
        assert report.ambiguous_routes.count("/x") == 2
