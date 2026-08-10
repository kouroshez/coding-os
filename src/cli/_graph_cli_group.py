"""Cross-repo groups and the static viewer: `cos graph-viz` and `cos graph-group`."""

from __future__ import annotations

import json
import os
from pathlib import Path

import click

from cli._graph_cli_shared import (
    _bootstrap_paths,
    _open_backend,
)


def _group_root(manifest_dir: str | None) -> Path:
    return (
        Path(manifest_dir).expanduser() if manifest_dir else (Path.home() / ".coding-os" / "groups")
    )


def _group_manifest_path(name: str, manifest_dir: str | None) -> Path:
    root = _group_root(manifest_dir)
    root.mkdir(parents=True, exist_ok=True)
    folder = root / name
    folder.mkdir(exist_ok=True)
    return folder / "group.json"


def _serve_static(path: Path, *, port: int, open_browser: bool) -> None:
    import socket
    import webbrowser
    from http.server import HTTPServer, SimpleHTTPRequestHandler

    os.chdir(path.parent)

    class _Handler(SimpleHTTPRequestHandler):
        def log_message(self, *_args, **_kwargs):
            pass

    if port == 0:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
    httpd = HTTPServer(("127.0.0.1", port), _Handler)
    url = f"http://127.0.0.1:{port}/{path.name}"
    click.echo(f"[serve] {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()
        click.echo("\n[serve] bye")


def register_group(cli: click.Group) -> None:
    """Attach this slice of the `cos graph-*` family onto `cli`."""

    @cli.command(name="graph-viz")
    @click.option("--path", default=None)
    @click.option("--out", default=None, help="Output HTML path.")
    @click.option("--root-uid", default=None)
    @click.option("--title", default="graph_os")
    @click.option("--bundled", is_flag=True)
    @click.option("--serve", is_flag=True)
    @click.option("--port", default=0, type=int)
    @click.option("--open/--no-open", "open_browser", default=True)
    def graph_viz(path, out, root_uid, title, bundled, serve, port, open_browser):
        """Generate the HTML graph viewer and optionally open / serve it."""
        _bootstrap_paths()
        from graph_os.ingest import walk_local  # type: ignore
        from graph_os.tools.reindex_dispatch import dispatch  # type: ignore
        from graph_os.viewer import build_view  # type: ignore

        backend, _ = _open_backend()
        if path:
            target = Path(path).expanduser().resolve()
            plan = walk_local(target)
            for file_path in plan.files:
                dispatch(file_path, project_root=target, include_docs=True)

        out_path = Path(out or Path(".coding-os") / "graph-viz.html").resolve()
        build_view(backend, out_path, title=title, root_uid=root_uid, bundled=bundled)
        click.echo(f"[graph-viz] wrote {out_path}")
        if serve:
            _serve_static(out_path, port=port, open_browser=open_browser)
        elif open_browser:
            import webbrowser

            webbrowser.open(out_path.as_uri())

    # ── group family --------------------------------------------------
    @cli.group(name="graph-group")
    def graph_group():
        """Cross-repo group operations."""

    @graph_group.command("create")
    @click.argument("name")
    @click.option(
        "--manifest-dir", default=None, help="Root for ~/.coding-os/groups/<name>/ overrides."
    )
    def group_create(name, manifest_dir):
        _bootstrap_paths()
        from graph_os.groups import GroupManifest, save_manifest  # type: ignore

        target = _group_manifest_path(name, manifest_dir)
        if target.exists():
            raise click.ClickException(f"group already exists at {target}")
        save_manifest(GroupManifest(name=name, members=[]), target)
        click.echo(f"[group] created {target}")

    @graph_group.command("add")
    @click.argument("name")
    @click.argument("path")
    @click.option("--alias", default=None)
    @click.option("--owns-route", multiple=True)
    @click.option("--manifest-dir", default=None)
    def group_add(name, path, alias, owns_route, manifest_dir):
        _bootstrap_paths()
        from graph_os.groups import load_manifest, register_member, save_manifest  # type: ignore

        target = _group_manifest_path(name, manifest_dir)
        if not target.exists():
            raise click.ClickException("group missing; run `cos graph-group create` first")
        manifest = load_manifest(target)
        alias = alias or Path(path).expanduser().resolve().name
        manifest = register_member(
            manifest,
            alias=alias,
            path=str(Path(path).expanduser().resolve()),
            owned_routes=list(owns_route),
        )
        save_manifest(manifest, target)
        click.echo(f"[group] added {alias} to {name}")

    @graph_group.command("list")
    @click.option("--manifest-dir", default=None)
    def group_list(manifest_dir):
        base = _group_root(manifest_dir)
        if not base.exists():
            click.echo("(no groups)")
            return
        for entry in sorted(base.iterdir()):
            if entry.is_dir() and (entry / "group.json").exists():
                click.echo(entry.name)

    @graph_group.command("status")
    @click.argument("name")
    @click.option("--manifest-dir", default=None)
    def group_status(name, manifest_dir):
        _bootstrap_paths()
        from graph_os.groups import load_manifest  # type: ignore

        target = _group_manifest_path(name, manifest_dir)
        if not target.exists():
            raise click.ClickException("group missing")
        manifest = load_manifest(target)
        payload = {
            "name": manifest.name,
            "members": [
                {
                    "alias": m.alias,
                    "path": m.path,
                    "exists": Path(m.path).exists(),
                    "owned_routes": m.owned_routes,
                }
                for m in manifest.members
            ],
        }
        click.echo(json.dumps(payload, indent=2))

    @graph_group.command("sync")
    @click.argument("name")
    @click.option("--manifest-dir", default=None)
    def group_sync(name, manifest_dir):
        _bootstrap_paths()
        from graph_os.groups import load_manifest  # type: ignore
        from graph_os.ingest import walk_local  # type: ignore
        from graph_os.tools.reindex_dispatch import dispatch  # type: ignore

        target = _group_manifest_path(name, manifest_dir)
        manifest = load_manifest(target)
        indexed = 0
        for member in manifest.members:
            root = Path(member.path)
            if not root.exists():
                click.echo(f"[sync] skip {member.alias} (missing: {root})", err=True)
                continue
            plan = walk_local(root)
            for file_path in plan.files:
                report = dispatch(file_path, project_root=root, include_docs=True)
                if report.get("status") == "ok":
                    indexed += 1
            click.echo(f"[sync] {member.alias}: {len(plan.files)} files")
        click.echo(f"[sync] indexed {indexed} entries total")
