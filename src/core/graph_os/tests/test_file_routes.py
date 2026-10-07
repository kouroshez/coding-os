"""File-based routes follow the router the package runs: Expo Router, Astro, TanStack Router, Next.js."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("tree_sitter_typescript")


def _manifest(*dependencies: str) -> str:
    return json.dumps({"dependencies": dict.fromkeys(dependencies, "1.0.0")})


FILES = {
    "apps/mobile/package.json": _manifest("expo-router", "react-native"),
    "apps/mobile/src/app/_layout.tsx": "export default function Root() { return null; }\n",
    "apps/mobile/src/app/(tabs)/index.tsx": "export default function HomeScreen() { return null; }\n",
    "apps/mobile/src/app/pet/[id].tsx": "export default function PetScreen() { return null; }\n",
    "apps/mobile/src/app/+not-found.tsx": "export default function NotFound() { return null; }\n",
    "apps/mobile/src/app/api/hello+api.ts": (
        "export async function GET(request: Request) { return Response.json({}); }\n"
        "export function POST(request: Request) { return Response.json({}); }\n"
    ),
    "apps/web/package.json": _manifest("astro"),
    "apps/web/src/pages/index.astro": "---\nconst title = 'Home';\n---\n<h1>{title}</h1>\n",
    "apps/web/src/pages/blog/[slug].astro": (
        "---\nexport async function getStaticPaths() {\n  return [];\n}\n---\n<article />\n"
    ),
    "apps/web/src/pages/api/feed.json.ts": (
        "import type { APIRoute } from 'astro';\n"
        "export const GET: APIRoute = async () => new Response('[]');\n"
    ),
    "apps/web/src/pages/_draft.astro": "---\n---\n<p />\n",
    "apps/admin/package.json": _manifest("@tanstack/react-router"),
    "apps/admin/src/routes/users.index.tsx": (
        "import { createFileRoute } from '@tanstack/react-router';\n"
        "export const Route = createFileRoute('/users/')({ component: UsersScreen });\n"
        "function UsersScreen() { return null; }\n"
    ),
    "apps/site/package.json": _manifest("react"),
    "apps/site/src/pages/About.tsx": "export default function About() { return null; }\n",
}


@pytest.fixture()
def db(tmp_path: Path) -> str:
    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend
    from graph_os.tools.reindex_dispatch import dispatch

    (tmp_path / ".coding-os").mkdir()
    for relative, text in FILES.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    database = str(tmp_path / "graph.db")
    for relative in FILES:
        dispatch(tmp_path / relative, project_root=tmp_path, db_path=database, include_docs=False)
    SqliteBackend(conn=init_db(database)).link_cross_file()
    return database


def _routes(db: str) -> dict[str, str]:
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT uid, json_extract(metadata_json, '$.framework') FROM graph_nodes "
            "WHERE kind = 'route'"
        ).fetchall()
    finally:
        conn.close()
    return dict(rows)


def _handlers(db: str) -> set[tuple[str, str]]:
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT s.uid, t.uid FROM graph_edges_v12 e JOIN graph_nodes s ON s.id = e.source_id "
            "JOIN graph_nodes t ON t.id = e.target_id WHERE s.kind = 'route' AND e.edge_type = 'calls'"
        ).fetchall()
    finally:
        conn.close()
    return {tuple(row) for row in rows}


def test_each_package_routes_by_its_own_router(db):
    assert _routes(db) == {
        "cos:route:GET:/": "astro",
        "cos:route:GET:/pet/{id}": "expo-router",
        "cos:route:GET:/api/hello": "expo-router",
        "cos:route:POST:/api/hello": "expo-router",
        "cos:route:GET:/blog/{slug}": "astro",
        "cos:route:GET:/api/feed.json": "astro",
        "cos:route:GET:/users/": "tanstack-router",
    }


def test_route_handlers_and_build_hooks_are_edges_not_dead_code(db):
    handlers = _handlers(db)

    assert (
        "cos:route:GET:/api/feed.json",
        "code:function:apps/web/src/pages/api/feed.json.ts::GET",
    ) in handlers
    assert (
        "cos:route:GET:/blog/{slug}",
        "code:function:apps/web/src/pages/blog/[slug].astro::getStaticPaths",
    ) in handlers
    assert (
        "cos:route:GET:/users/",
        "code:function:apps/admin/src/routes/users.index.tsx::UsersScreen",
    ) in handlers


FORMS = {
    "apps/mobile/package.json": _manifest("expo-router"),
    "apps/mobile/src/app/profile.tsx": "export { default } from '../screens/Profile';\n",
    "apps/mobile/src/app/settings.tsx": "const Settings = () => null;\nexport default Settings;\n",
    "apps/mobile/src/screens/Profile.tsx": "export default function Profile() { return null; }\n",
    "apps/web/package.json": _manifest("astro"),
    "apps/web/src/pages/_partials/nav.astro": "---\n---\n<nav />\n",
    "apps/web/src/pages/[lang]-[slug].astro": "---\n---\n<p />\n",
    "apps/web/src/pages/api/[id].json.ts": "export const GET = () => new Response('{}');\n",
    "apps/web/src/pages/api/legacy.ts": "const handle = () => new Response('');\nexport { handle as POST };\n",
    "apps/web/src/pages/about.md": "# About\n",
    "apps/web/src/pages/guide.mdx": "# Guide\n",
    "apps/admin/package.json": _manifest("@tanstack/react-router"),
    "apps/admin/src/router.tsx": (
        "import { createRootRoute, createRoute } from '@tanstack/react-router';\n"
        "const rootRoute = createRootRoute();\n"
        "const postsRoute = createRoute({ getParentRoute: () => rootRoute, path: 'posts', component: Posts });\n"
        "const postRoute = createRoute({ getParentRoute: () => postsRoute, path: '$postId', component: Post });\n"
        "function Posts() { return null; }\n"
        "function Post() { return null; }\n"
    ),
}


def test_route_forms_beyond_the_plain_file(tmp_path: Path):
    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend
    from graph_os.tools.reindex_dispatch import dispatch

    (tmp_path / ".coding-os").mkdir()
    for relative, text in FORMS.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    database = str(tmp_path / "graph.db")
    for relative in FORMS:
        dispatch(tmp_path / relative, project_root=tmp_path, db_path=database, include_docs=False)
    SqliteBackend(conn=init_db(database)).link_cross_file()

    assert set(_routes(database)) == {
        "cos:route:GET:/profile",
        "cos:route:GET:/settings",
        "cos:route:GET:/{lang}-{slug}",
        "cos:route:GET:/api/{id}.json",
        "cos:route:POST:/api/legacy",
        "cos:route:GET:/about",
        "cos:route:GET:/guide",
        "cos:route:GET:/posts",
        "cos:route:GET:/posts/$postId",
    }
    assert (
        "cos:route:GET:/settings",
        "code:function:apps/mobile/src/app/settings.tsx::Settings",
    ) in _handlers(database)
