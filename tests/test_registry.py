"""Tests for cli.registry — global coding-os project registry."""

from __future__ import annotations

import json
import os
from pathlib import Path

import click
import pytest

from cli.registry import (
    Registry,
    add_project,
    load_registry,
    registry_path,
    remove_project,
    save_registry,
)


@pytest.fixture
def tmp_registry(tmp_path, monkeypatch):
    """Redirect the global registry to a tmp file for isolation."""
    path = tmp_path / "registry.json"
    monkeypatch.setenv("COS_REGISTRY_PATH", str(path))
    return path


def test_load_registry_returns_empty_when_missing(tmp_registry):
    reg = load_registry()
    assert reg.projects == []
    assert reg.version == 1


def test_save_and_load_roundtrip(tmp_registry):
    reg = Registry()
    save_registry(reg)
    assert tmp_registry.exists()
    loaded = load_registry()
    assert loaded.version == reg.version


def test_add_project_creates_entry(tmp_path, tmp_registry):
    project = tmp_path / "demo"
    (project / ".coding-os").mkdir(parents=True)
    entry = add_project(project)
    assert entry.slug == "demo"
    assert Path(entry.path) == project.resolve()
    # File exists with the entry
    data = json.loads(tmp_registry.read_text())
    assert len(data["projects"]) == 1


def test_add_project_is_idempotent_on_path(tmp_path, tmp_registry):
    project = tmp_path / "alpha"
    (project / ".coding-os").mkdir(parents=True)
    first = add_project(project)
    second = add_project(project)
    assert first == second
    reg = load_registry()
    assert len(reg.projects) == 1


def test_add_project_slug_collision_raises(tmp_path, tmp_registry):
    p1 = tmp_path / "one" / "proj"
    p2 = tmp_path / "two" / "proj"
    p1.mkdir(parents=True)
    p2.mkdir(parents=True)
    add_project(p1)
    with pytest.raises(click.ClickException):
        add_project(p2)  # same slug "proj", different path


def test_remove_project_by_slug(tmp_path, tmp_registry):
    project = tmp_path / "to-remove"
    (project / ".coding-os").mkdir(parents=True)
    add_project(project)
    removed = remove_project("to-remove")
    assert removed is not None
    assert removed.slug == "to-remove"
    assert load_registry().projects == []


def test_remove_project_missing_returns_none(tmp_registry):
    assert remove_project("does-not-exist") is None


def test_registry_path_honours_env_override(tmp_path, monkeypatch):
    target = tmp_path / "custom" / "registry.json"
    monkeypatch.setenv("COS_REGISTRY_PATH", str(target))
    assert registry_path() == target.resolve()


def test_malformed_json_raises(tmp_registry):
    tmp_registry.write_text("not json", encoding="utf-8")
    with pytest.raises(click.ClickException):
        load_registry()
