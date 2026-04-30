"""Generate a FastAPI endpoint scaffold per `references/anatomy.md`.

PURPOSE:      Emit Router + Schema + Service + Test stubs in one shot.
INPUT:        --resource <name>  — resource (snake_case).
              [--root <dir>]     — defaults to `backend/`.
OUTPUT:       Four files: api/<resource>.py, schemas/<resource>.py,
              services/<resource>.py, tests/test_<resource>_api.py.
DEPENDENCIES: stdlib only.
NOTES:        Idempotent — refuses to overwrite existing files. Agent
              wires the router into main.py manually (one-line edit).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _pascal(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_") if part)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--resource", required=True)
    parser.add_argument("--root", default="backend")
    args = parser.parse_args()

    root = Path(args.root)
    api_dir = root / "api"
    schemas_dir = root / "schemas"
    services_dir = root / "services"
    tests_dir = root / "tests"
    for d in (api_dir, schemas_dir, services_dir, tests_dir):
        d.mkdir(parents=True, exist_ok=True)

    pascal = _pascal(args.resource)
    api_path = api_dir / f"{args.resource}.py"
    schema_path = schemas_dir / f"{args.resource}.py"
    service_path = services_dir / f"{args.resource}.py"
    test_path = tests_dir / f"test_{args.resource}_api.py"

    for p in (api_path, schema_path, service_path, test_path):
        if p.exists():
            print(f"ERROR: refuse to overwrite existing file: {p}", file=sys.stderr)
            return 1

    schema_path.write_text(
        f"from pydantic import BaseModel\n\n\n"
        f"class {pascal}In(BaseModel):\n"
        f"    # TODO: request fields\n"
        f"    pass\n\n\n"
        f"class {pascal}Out(BaseModel):\n"
        f"    # TODO: response fields\n"
        f"    pass\n",
        encoding="utf-8",
    )
    service_path.write_text(
        f"from ..schemas.{args.resource} import {pascal}In, {pascal}Out\n\n\n"
        f"async def create_{args.resource}(payload: {pascal}In) -> {pascal}Out:\n"
        f"    # TODO: business logic\n"
        f"    return {pascal}Out()\n",
        encoding="utf-8",
    )
    api_path.write_text(
        f"from fastapi import APIRouter, status\n\n"
        f"from ..schemas.{args.resource} import {pascal}In, {pascal}Out\n"
        f"from ..services.{args.resource} import create_{args.resource}\n\n"
        f"router = APIRouter(prefix=\"/{args.resource}\", tags=[\"{args.resource}\"])\n\n\n"
        f"@router.post(\"/\", response_model={pascal}Out, status_code=status.HTTP_201_CREATED)\n"
        f"async def create(payload: {pascal}In) -> {pascal}Out:\n"
        f"    return await create_{args.resource}(payload)\n",
        encoding="utf-8",
    )
    test_path.write_text(
        f"import pytest\n"
        f"from httpx import AsyncClient\n\n"
        f"# from main import app  # TODO: import the real app instance\n\n\n"
        f"@pytest.mark.asyncio\n"
        f"async def test_create_{args.resource}_returns_201():\n"
        f"    # Given: a valid payload\n"
        f"    payload = {{}}\n"
        f"    # When: POST /{args.resource}/\n"
        f"    # async with AsyncClient(app=app, base_url=\"http://test\") as ac:\n"
        f"    #     resp = await ac.post(\"/{args.resource}/\", json=payload)\n"
        f"    # Then:\n"
        f"    # assert resp.status_code == 201\n"
        f"    assert payload == {{}}  # placeholder until app wiring\n",
        encoding="utf-8",
    )
    print(f"OK: wrote {schema_path}")
    print(f"OK: wrote {service_path}")
    print(f"OK: wrote {api_path}")
    print(f"OK: wrote {test_path}")
    print(f"INFO: include the router in {root}/main.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
