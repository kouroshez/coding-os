"""Tests for the wordpress scan_wp_smells.py scanner."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "src" / "core" / "skills" / "wordpress" / "scripts"),
)

import scan_wp_smells as sw  # noqa: E402

SECURE = """<?php
function mp_save() {
    check_admin_referer('mp_save');
    if (!current_user_can('edit_posts')) wp_die();
    $t = sanitize_text_field($_POST['t']);
    update_post_meta($id, 't', $t);
}
"""


def test_secure_handler_clean() -> None:
    assert sw.scan_text(SECURE, filename="ok.php") == []


def test_missing_nonce_flagged() -> None:
    php = "<?php\nfunction f(){ if(current_user_can('x')){ $t=$_POST['t']; } }"
    out = sw.scan_text(php, filename="x.php")
    assert any("nonce" in f for f in out)


def test_missing_capability_flagged() -> None:
    php = "<?php\nfunction f(){ check_admin_referer('x'); $t=$_POST['t']; }"
    out = sw.scan_text(php, filename="x.php")
    assert any("capability" in f for f in out)


def test_raw_wpdb_query_flagged() -> None:
    php = "<?php\n$wpdb->query(\"SELECT * FROM x WHERE id=$_GET[id]\");\ncheck_admin_referer('a');\ncurrent_user_can('b');"
    out = sw.scan_text(php, filename="x.php")
    assert any("$wpdb" in f for f in out)


def test_return_true_permission_flagged() -> None:
    php = "<?php\n register_rest_route('a','/b',['permission_callback'=>'__return_true']);"
    out = sw.scan_text(php, filename="x.php")
    assert any("__return_true" in f for f in out)


def test_no_request_no_trinity_findings() -> None:
    php = "<?php\nfunction helper(){ return 1 + 1; }"
    assert sw.scan_text(php, filename="x.php") == []
