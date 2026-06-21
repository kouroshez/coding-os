"""Tests for the supabase check_rls.py RLS scanner."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "src" / "core" / "skills" / "supabase" / "scripts")
)

import check_rls as cr  # noqa: E402


def test_table_with_rls_is_clean() -> None:
    sql = """
    create table notes (id uuid primary key, user_id uuid);
    alter table notes enable row level security;
    """
    assert cr.scan(sql) == []


def test_table_without_rls_flagged() -> None:
    sql = "create table notes (id uuid primary key, user_id uuid);"
    assert cr.scan(sql) == ["notes"]


def test_if_not_exists_and_schema_qualified() -> None:
    sql = """
    create table if not exists public.profiles (id uuid);
    alter table public.profiles enable row level security;
    create table public.secrets (id uuid);
    """
    assert cr.scan(sql) == ["secrets"]


def test_non_public_schema_ignored_by_default() -> None:
    sql = "create table auth.sessions (id uuid);"
    assert cr.scan(sql) == []


def test_comments_do_not_confuse_parser() -> None:
    sql = """
    -- create table ghost (id uuid);
    /* create table phantom (id uuid); */
    create table real_t (id uuid);
    alter table real_t enable row level security;
    """
    assert cr.scan(sql) == []


def test_quoted_identifiers() -> None:
    sql = 'create table "Notes" (id uuid); alter table "Notes" enable row level security;'
    assert cr.scan(sql) == []
