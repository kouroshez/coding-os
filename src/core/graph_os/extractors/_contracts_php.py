"""PHP contract scanners — Laravel routes, WordPress hooks, WHMCS entry points.

One ecosystem per module: adding a Laravel form or a new WP hook shape should
never put the Go or TypeScript scanners in the diff.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from ._contracts_shared import _STRING_CAPTURE, ContractMatch, _join_paths, _line_of

# PHP frameworks — Laravel / WordPress / WHMCS
# ---------------------------------------------------------------------------

# Laravel: Route::get('/x', handler). `match`/group-closure handled below.
_LARAVEL_ROUTE_RE = re.compile(
    rf"""Route::(?P<method>get|post|put|patch|delete|options|any)\s*\(\s*{_STRING_CAPTURE}""",
    re.VERBOSE,
)
_LARAVEL_RESOURCE_RE = re.compile(
    rf"""Route::(?P<kind>apiResource|resource)\s*\(\s*{_STRING_CAPTURE}\s*,\s*
        (?P<ctrl>[A-Za-z_\\][\w\\]*)::class
    """,
    re.VERBOSE,
)
# Handler arg right after the route path string.
_LARAVEL_H_ARRAY_RE = re.compile(
    r"""^\s*,\s*\[\s*(?P<ctrl>[A-Za-z_\\][\w\\]*)::class\s*,\s*['"](?P<method>\w+)['"]"""
)
_LARAVEL_H_STRING_RE = re.compile(r"""^\s*,\s*['"](?P<ctrl>[A-Za-z_\\][\w]*)@(?P<method>\w+)['"]""")
_LARAVEL_H_INVOKE_RE = re.compile(r"""^\s*,\s*(?P<ctrl>[A-Za-z_\\][\w\\]*)::class\s*[\),]""")
_LARAVEL_SIGNATURE_RE = re.compile(r"""\$signature\s*=\s*['"](?P<sig>[^'"]+)['"]""")

# resource → 7 RESTful routes; apiResource → 5 (no create/edit).
_LARAVEL_RESOURCE_ACTIONS = {
    "resource": [
        ("get", "", "index"),
        ("get", "/create", "create"),
        ("post", "", "store"),
        ("get", "/{id}", "show"),
        ("get", "/{id}/edit", "edit"),
        ("put", "/{id}", "update"),
        ("delete", "/{id}", "destroy"),
    ],
    "apiResource": [
        ("get", "", "index"),
        ("post", "", "store"),
        ("get", "/{id}", "show"),
        ("put", "/{id}", "update"),
        ("delete", "/{id}", "destroy"),
    ],
}


def _php_short_name(name: str) -> str:
    return name.replace("/", "\\").split("\\")[-1]


# Group-closure scoping — fluent `Route::prefix('x')->group(function(){...})`
# and array `Route::group(['prefix'=>'x'], function(){...})`.
_LARAVEL_GROUP_FLUENT_RE = re.compile(
    r"""Route::(?P<chain>[^;]*?)->group\s*\(\s*(?:function|fn)\b[^{]*\{""", re.VERBOSE
)
_LARAVEL_GROUP_ARRAY_RE = re.compile(
    r"""Route::group\s*\(\s*\[(?P<arr>[^\]]*)\][^{]*\{""", re.VERBOSE
)
_LARAVEL_PREFIX_IN_CHAIN_RE = re.compile(r"""prefix\(\s*['"](?P<p>[^'"]+)['"]""")
_LARAVEL_PREFIX_IN_ARRAY_RE = re.compile(r"""['"]prefix['"]\s*=>\s*['"](?P<p>[^'"]+)['"]""")


def _match_brace(content: str, open_idx: int) -> int:
    """Index of the `}` matching the `{` at open_idx, skipping strings/comments."""
    depth = 0
    i = open_idx
    n = len(content)
    while i < n:
        c = content[i]
        if c in "'\"":
            q = c
            i += 1
            while i < n and content[i] != q:
                if content[i] == "\\":
                    i += 1
                i += 1
            i += 1
            continue
        if c == "/" and i + 1 < n and content[i + 1] == "/":
            while i < n and content[i] != "\n":
                i += 1
            continue
        if c == "#":
            while i < n and content[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and content[i + 1] == "*":
            i += 2
            while i + 1 < n and not (content[i] == "*" and content[i + 1] == "/"):
                i += 1
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n


def _laravel_group_spans(content: str) -> list[tuple[int, int, str]]:
    """(open_brace_idx, close_brace_idx, prefix) for every Route group closure."""
    spans: list[tuple[int, int, str]] = []
    for m in _LARAVEL_GROUP_FLUENT_RE.finditer(content):
        pm = _LARAVEL_PREFIX_IN_CHAIN_RE.search(m.group("chain"))
        open_idx = m.end() - 1
        spans.append((open_idx, _match_brace(content, open_idx), pm.group("p") if pm else ""))
    for m in _LARAVEL_GROUP_ARRAY_RE.finditer(content):
        pm = _LARAVEL_PREFIX_IN_ARRAY_RE.search(m.group("arr"))
        open_idx = m.end() - 1
        spans.append((open_idx, _match_brace(content, open_idx), pm.group("p") if pm else ""))
    return spans


def _laravel_group_prefix(spans: list[tuple[int, int, str]], pos: int) -> str:
    """Joined prefix of all group closures containing pos (outer→inner)."""
    containing = sorted((s for s in spans if s[0] < pos < s[1] and s[2]), key=lambda s: s[0])
    prefix = ""
    for _, _, p in containing:
        prefix = _join_paths(prefix, p) if prefix else "/" + p.strip("/")
    return prefix


def _laravel_handler(content: str, end: int) -> str | None:
    tail = content[end:]
    m = _LARAVEL_H_ARRAY_RE.match(tail)
    if m:
        return f"{_php_short_name(m.group('ctrl'))}@{m.group('method')}"
    m = _LARAVEL_H_STRING_RE.match(tail)
    if m:
        return f"{_php_short_name(m.group('ctrl'))}@{m.group('method')}"
    m = _LARAVEL_H_INVOKE_RE.match(tail)
    if m:
        return f"{_php_short_name(m.group('ctrl'))}@__invoke"
    return None


def _scan_laravel(content: str) -> list[ContractMatch]:
    """Laravel routes (facade + resource) + Artisan commands.

    Note: routes nested in `Route::prefix(..)->group(..)` closures are
    captured at their literal path — the group prefix is NOT auto-joined
    (closure scoping needs an AST, not regex), so no FALSE prefixes appear.
    """
    if (
        "Route::" not in content
        and "Illuminate\\" not in content
        and "extends Command" not in content
    ):
        return []
    hits: list[ContractMatch] = []
    spans = _laravel_group_spans(content)
    for m in _LARAVEL_ROUTE_RE.finditer(content):
        method = m.group("method").lower()
        prefix = _laravel_group_prefix(spans, m.start())
        path = _join_paths(prefix, m.group("path")) if prefix else m.group("path")
        hits.append(
            ContractMatch(
                kind="http",
                framework="laravel",
                method="any" if method == "any" else method,
                path=path,
                handler=_laravel_handler(content, m.end()),
                line=_line_of(content, m.start()),
            )
        )
    for m in _LARAVEL_RESOURCE_RE.finditer(content):
        name = m.group("path").strip("/")
        ctrl = _php_short_name(m.group("ctrl"))
        line = _line_of(content, m.start())
        prefix = _laravel_group_prefix(spans, m.start())
        for method, suffix, action in _LARAVEL_RESOURCE_ACTIONS[m.group("kind")]:
            base = _join_paths(prefix, f"/{name}{suffix}") if prefix else f"/{name}{suffix}"
            hits.append(
                ContractMatch(
                    kind="http",
                    framework="laravel",
                    method=method,
                    path=base,
                    handler=f"{ctrl}@{action}",
                    line=line,
                    confidence=0.85,
                    derivation=f"laravel_{m.group('kind')}",
                )
            )
    if "extends Command" in content:
        for m in _LARAVEL_SIGNATURE_RE.finditer(content):
            cmd = m.group("sig").split()[0] if m.group("sig") else m.group("sig")
            hits.append(
                ContractMatch(
                    kind="cli",
                    framework="artisan",
                    method="command",
                    path=cmd,
                    handler=None,
                    line=_line_of(content, m.start()),
                )
            )
    return hits


_WP_HOOK_RE = re.compile(
    rf"""\badd_(?P<typ>action|filter)\s*\(\s*{_STRING_CAPTURE}
        (?:\s*,\s*['"]?(?P<cb>[A-Za-z_][\w]*)['"]?)?
    """,
    re.VERBOSE,
)
_WP_FIRE_RE = re.compile(
    rf"""\b(?P<typ>do_action|apply_filters)\s*\(\s*{_STRING_CAPTURE}""", re.VERBOSE
)
_WP_SHORTCODE_RE = re.compile(rf"""\badd_shortcode\s*\(\s*{_STRING_CAPTURE}""", re.VERBOSE)
_WP_CPT_RE = re.compile(rf"""\bregister_post_type\s*\(\s*{_STRING_CAPTURE}""", re.VERBOSE)
_WP_REST_RE = re.compile(
    r"""\bregister_rest_route\s*\(\s*['"](?P<ns>[^'"]+)['"]\s*,\s*['"](?P<route>[^'"]+)['"]
        (?:[^)]*?['"]methods['"]\s*=>\s*['"](?P<methods>[^'"]+)['"])?
    """,
    re.VERBOSE | re.DOTALL,
)
_WP_MARKERS = (
    "add_action",
    "add_filter",
    "add_shortcode",
    "register_post_type",
    "register_rest_route",
    "do_action",
    "apply_filters",
)


def _scan_wordpress(content: str) -> list[ContractMatch]:
    """WordPress hooks (action/filter + fire sites), shortcodes, CPT, REST, ajax."""
    if not any(tok in content for tok in _WP_MARKERS):
        return []
    hits: list[ContractMatch] = []
    for m in _WP_HOOK_RE.finditer(content):
        hook = m.group("path")
        cb = m.group("cb")
        if cb in ("array", "function", "fn"):
            cb = None  # array($this,'m') / closure — not a bare function handler
        line = _line_of(content, m.start())
        if hook.startswith("wp_ajax_"):
            action = (
                hook[len("wp_ajax_nopriv_") :]
                if hook.startswith("wp_ajax_nopriv_")
                else hook[len("wp_ajax_") :]
            )
            hits.append(
                ContractMatch(
                    kind="http",
                    framework="wp_ajax",
                    method="post",
                    path=f"/wp-admin/admin-ajax.php?action={action}",
                    handler=cb,
                    line=line,
                    derivation="wp_ajax",
                )
            )
        else:
            hits.append(
                ContractMatch(
                    kind="event",
                    framework=f"wp_{m.group('typ')}",
                    method=m.group("typ"),
                    path=hook,
                    handler=cb,
                    line=line,
                )
            )
    for m in _WP_FIRE_RE.finditer(content):
        hits.append(
            ContractMatch(
                kind="event",
                framework="wp_emit",
                method=m.group("typ"),
                path=m.group("path"),
                handler=None,
                line=_line_of(content, m.start()),
                derivation="wp_fire",
            )
        )
    for m in _WP_SHORTCODE_RE.finditer(content):
        hits.append(
            ContractMatch(
                kind="event",
                framework="wp_shortcode",
                method="shortcode",
                path=m.group("path"),
                handler=None,
                line=_line_of(content, m.start()),
            )
        )
    for m in _WP_CPT_RE.finditer(content):
        hits.append(
            ContractMatch(
                kind="event",
                framework="wp_cpt",
                method="post_type",
                path=m.group("path"),
                handler=None,
                line=_line_of(content, m.start()),
            )
        )
    for m in _WP_REST_RE.finditer(content):
        ns = m.group("ns").strip("/")
        route = m.group("route")
        method = (m.group("methods") or "any").split(",")[0].strip().lower()
        hits.append(
            ContractMatch(
                kind="http",
                framework="wp_rest",
                method=method,
                path=_join_paths(f"/wp-json/{ns}", route),
                handler=None,
                line=_line_of(content, m.start()),
                derivation="wp_rest",
            )
        )
    return hits


_WHMCS_ADD_HOOK_RE = re.compile(
    rf"""\badd_hook\s*\(\s*{_STRING_CAPTURE}\s*,\s*\d+
        (?:\s*,\s*['"]?(?P<cb>[A-Za-z_][\w]*)['"]?)?
    """,
    re.VERBOSE,
)
_WHMCS_DIRS = {
    "modules/servers/": "provisioning",
    "modules/registrars/": "registrar",
    "modules/addons/": "addon",
    "modules/gateways/": "gateway",
}


def _scan_whmcs(content: str, *, path: str) -> list[ContractMatch]:
    """WHMCS `add_hook(...)` + module-function convention `{module}_{Action}`."""
    module_type = next((mt for d, mt in _WHMCS_DIRS.items() if d in path), "")
    has_hook = "add_hook(" in content
    if not module_type and not has_hook:
        return []
    hits: list[ContractMatch] = []
    for m in _WHMCS_ADD_HOOK_RE.finditer(content):
        hits.append(
            ContractMatch(
                kind="event",
                framework="whmcs_hook",
                method="hook",
                path=m.group("path"),
                handler=m.group("cb"),
                line=_line_of(content, m.start()),
                derivation="whmcs_hook",
            )
        )
    # Module-function convention: only inside a recognised module path, where
    # `{module}` == the file stem (servers/registrars/addons → {name}/{name}.php;
    # gateways → {name}.php). Avoids false-matching `prefix_foo` elsewhere.
    if module_type:
        module = PurePosixPath(path).stem
        if module:
            fn_re = re.compile(rf"\bfunction\s+(?P<fn>{re.escape(module)}_\w+)\s*\(")
            for m in fn_re.finditer(content):
                fn = m.group("fn")
                action = fn[len(module) + 1 :]
                hits.append(
                    ContractMatch(
                        kind="event",
                        framework=f"whmcs_{module_type}",
                        method="module_fn",
                        path=fn,
                        handler=fn,
                        line=_line_of(content, m.start()),
                        derivation="whmcs_module",
                        note=action,
                    )
                )
    return hits
