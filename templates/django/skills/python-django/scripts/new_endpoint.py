"""Generate a Django DRF endpoint scaffold per `references/anatomy.md`.

PURPOSE:      Emit ViewSet + Serializer + Test stubs in one shot so the
              agent never has to remember the exact 4-file layout.
INPUT:        --app <name>     — Django app name under `backend/`.
              --entity <name>  — entity / resource name (snake_case).
              [--root <dir>]   — defaults to `backend/`.
OUTPUT:       Three files: views/<entity>.py, serializers/<entity>.py,
              tests/test_<entity>_views.py. URLs not auto-edited — agent
              must wire the router manually (one-line edit).
DEPENDENCIES: stdlib only.
NOTES:        Idempotent — refuses to overwrite existing files.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _pascal(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_") if part)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--app", required=True)
    parser.add_argument("--entity", required=True)
    parser.add_argument("--root", default="backend")
    args = parser.parse_args()

    app_root = Path(args.root) / args.app
    views_dir = app_root / "views"
    serializers_dir = app_root / "serializers"
    tests_dir = app_root / "tests"
    for d in (views_dir, serializers_dir, tests_dir):
        d.mkdir(parents=True, exist_ok=True)

    pascal = _pascal(args.entity)
    view_path = views_dir / f"{args.entity}.py"
    serializer_path = serializers_dir / f"{args.entity}.py"
    test_path = tests_dir / f"test_{args.entity}_views.py"

    for p in (view_path, serializer_path, test_path):
        if p.exists():
            print(f"ERROR: refuse to overwrite existing file: {p}", file=sys.stderr)
            return 1

    serializer_path.write_text(
        f"from rest_framework import serializers\n\n\n"
        f"class {pascal}Serializer(serializers.Serializer):\n"
        f"    # TODO: declare fields\n"
        f"    pass\n",
        encoding="utf-8",
    )
    view_path.write_text(
        f"from rest_framework import viewsets\n"
        f"from rest_framework.permissions import IsAuthenticated\n\n"
        f"from ..serializers.{args.entity} import {pascal}Serializer\n\n\n"
        f"class {pascal}ViewSet(viewsets.ViewSet):\n"
        f"    permission_classes = [IsAuthenticated]\n"
        f"    serializer_class = {pascal}Serializer\n"
        f"    # TODO: implement list / retrieve / create / update / destroy\n",
        encoding="utf-8",
    )
    test_path.write_text(
        f"import pytest\n"
        f"from rest_framework.test import APIClient\n\n\n"
        f"@pytest.mark.django_db\n"
        f"class Test{pascal}ViewSet:\n"
        f"    def test_list_requires_auth(self):\n"
        f"        # Given: an unauthenticated client\n"
        f"        client = APIClient()\n"
        f"        # When: it calls list\n"
        f"        response = client.get('/api/{args.entity}/')\n"
        f"        # Then: 401 (or 403 with TokenAuth)\n"
        f"        assert response.status_code in (401, 403)\n",
        encoding="utf-8",
    )
    print(f"OK: wrote {serializer_path}")
    print(f"OK: wrote {view_path}")
    print(f"OK: wrote {test_path}")
    print(f"INFO: wire the router manually in {app_root}/urls.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
