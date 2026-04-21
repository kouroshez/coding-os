"""
Tests for concept extraction and spreading activation (TASK-158).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import init_db
from concepts import extract_concepts, spread_activation


class TestExtractConcepts:
    def test_backend_model_file(self) -> None:
        concepts = extract_concepts(file_path="backend/apps/products/models.py")
        assert "products" in concepts
        assert "django" in concepts

    def test_frontend_component(self) -> None:
        concepts = extract_concepts(file_path="frontend/src/components/Button.tsx")
        assert "react" in concepts
        assert "button" in concepts

    def test_migration_file(self) -> None:
        concepts = extract_concepts(file_path="backend/apps/products/migrations/0001.py")
        assert "migration" in concepts

    def test_domain_added(self) -> None:
        concepts = extract_concepts(file_path="some/file.py", domain="BACKEND")
        assert "backend" in concepts

    def test_stop_words_excluded(self) -> None:
        concepts = extract_concepts(file_path="apps/src/utils/index.py")
        assert "apps" not in concepts
        assert "src" not in concepts
        assert "utils" not in concepts

    def test_max_7_concepts(self) -> None:
        concepts = extract_concepts(
            file_path="backend/apps/products/services/payments/stripe/webhooks/handlers.py",
            domain="BACKEND",
        )
        assert len(concepts) <= 7

    def test_empty_path(self) -> None:
        concepts = extract_concepts(file_path="")
        assert isinstance(concepts, list)

    def test_serializer_gets_api_concept(self) -> None:
        concepts = extract_concepts(file_path="backend/apps/products/serializers.py")
        assert "api" in concepts


class TestSpreadActivation:
    @pytest.fixture
    def conn(self, tmp_path: Path) -> sqlite3.Connection:
        c = init_db(tmp_path / "test.db")
        # Insert patterns with concepts
        patterns = [
            ("Django ORM optimization", '["django","orm","optimization"]', 0.7),
            ("React state management", '["react","state","hooks"]', 0.6),
            ("Django migration best practices", '["django","migration","schema"]', 0.8),
            ("API error handling", '["api","django","error"]', 0.5),
            ("Low confidence pattern", '["django","celery"]', 0.1),
        ]
        for pattern, concepts, conf in patterns:
            c.execute(
                "INSERT INTO learned_patterns (pattern, concepts, confidence, domain) "
                "VALUES (?, ?, ?, ?)",
                (pattern, concepts, conf, "BACKEND"),
            )
        c.commit()
        yield c
        c.close()

    def test_finds_related_patterns(self, conn) -> None:
        # Source concepts from a "Django model" search result
        results = spread_activation(
            conn,
            top_result_ids={1},  # exclude ORM optimization
            source_concepts={"django", "orm", "migration"},
        )
        assert len(results) > 0
        # Should find Django migration pattern (shares django + migration)
        titles = [r["title"] for r in results]
        assert any("migration" in t.lower() for t in titles)

    def test_excludes_top_results(self, conn) -> None:
        results = spread_activation(
            conn,
            top_result_ids={1, 3},  # exclude both Django patterns
            source_concepts={"django", "orm", "migration"},
        )
        ids = {r["id"] for r in results}
        assert 1 not in ids
        assert 3 not in ids

    def test_requires_min_overlap(self, conn) -> None:
        # Only 1 concept overlap — should not match
        results = spread_activation(
            conn,
            top_result_ids=set(),
            source_concepts={"react"},  # only 1 concept
            min_overlap=2,
        )
        assert len(results) == 0

    def test_excludes_low_confidence(self, conn) -> None:
        results = spread_activation(
            conn,
            top_result_ids=set(),
            source_concepts={"django", "celery"},
        )
        # Pattern 5 has confidence 0.1, below 0.2 threshold
        ids = {r["id"] for r in results}
        assert 5 not in ids

    def test_empty_concepts(self, conn) -> None:
        results = spread_activation(
            conn,
            top_result_ids=set(),
            source_concepts=set(),
        )
        assert results == []

    def test_spread_weight_05(self, conn) -> None:
        results = spread_activation(
            conn,
            top_result_ids={1},
            source_concepts={"django", "orm", "migration"},
        )
        for r in results:
            assert r["spread_weight"] == 0.5

    def test_overlap_concepts_returned(self, conn) -> None:
        results = spread_activation(
            conn,
            top_result_ids={1},
            source_concepts={"django", "orm", "migration"},
        )
        if results:
            assert "overlap_concepts" in results[0]
            assert len(results[0]["overlap_concepts"]) >= 2

    def test_limit_respected(self, conn) -> None:
        results = spread_activation(
            conn,
            top_result_ids=set(),
            source_concepts={"django", "orm", "migration", "api", "error"},
            limit=2,
        )
        assert len(results) <= 2
