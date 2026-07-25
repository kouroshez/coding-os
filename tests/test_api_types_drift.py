"""Drift gate for the generated Hub API types.

`src/core/web/ui/src/lib/api-client.ts` derives `ApiPath` from the generated
`api-types.ts`, so every SPA call site is typechecked against the routes the
backend really serves. That guarantee is only as fresh as the generated file:
regenerate with `npm run gen-api` (hub up on :9188) after adding, renaming, or
deleting a route.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "src" / "core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from web.server import create_app

API_TYPES = _REPO_ROOT / "src" / "core" / "web" / "ui" / "src" / "lib" / "api-types.ts"
_PATH_KEY = re.compile(r'^    "(/[^"]*)": \{', re.MULTILINE)
_REGEN = "regenerate with: cd src/core/web/ui && npm run gen-api  (hub up on :9188)"


def _served_paths() -> set[str]:
    return set(create_app().openapi()["paths"])


def _generated_paths() -> set[str]:
    return set(_PATH_KEY.findall(API_TYPES.read_text()))


def test_generated_types_cover_every_served_route() -> None:
    missing = _served_paths() - _generated_paths()
    assert not missing, (
        f"api-types.ts is stale — {len(missing)} route(s) the app serves are absent, "
        f"so ApiPath rejects a valid path: {sorted(missing)}\n{_REGEN}"
    )


def test_generated_types_have_no_routes_the_app_dropped() -> None:
    extra = _generated_paths() - _served_paths()
    assert not extra, (
        f"api-types.ts is stale — {len(extra)} route(s) no longer exist, so ApiPath "
        f"still accepts a dead path: {sorted(extra)}\n{_REGEN}"
    )
