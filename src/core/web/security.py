"""core.web.security — localhost security gate (Origin/Host allowlist + CSRF).

The hub binds 127.0.0.1 but is unauthenticated, so any page the user's
browser visits can issue requests at it. Once mutation routes exist
(registry add/scan/gc, the filesystem-scaffolding init route) two
browser-mediated threats apply: DNS rebinding and CSRF.

`SecurityGateMiddleware` is **browser-evidence-gated** — it only engages
for requests carrying an Origin or Referer header. Non-browser clients
(curl, server-to-server, MCP, the test client) never send those and are
not the CSRF/rebinding vector, so they pass through. Contract:
docs/engineering/hub-architecture.md#localhost-security-gate-originhost-allowlist--csrf
"""

from __future__ import annotations

import os
import secrets
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

CSRF_COOKIE = "cos_csrf"
CSRF_HEADER = "x-csrf-token"
_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_BASE_ALLOWED_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _allowed_hosts() -> frozenset[str]:
    extra = os.environ.get("COS_WEB_ALLOWED_HOSTS", "")
    names = {h.strip().lower() for h in extra.split(",") if h.strip()}
    return _BASE_ALLOWED_HOSTS | names


class InsecureBindError(RuntimeError):
    """Raised when the hub would listen off-loopback with no credential."""


def _is_loopback_bind(host: str) -> bool:
    import ipaddress

    name = host.strip().lower()
    if not name or name == "localhost":
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        # A hostname we cannot classify: treat as exposed. Guessing "probably
        # local" is the assumption that leaves an API open.
        return False


def assert_bind_is_safe(host: str, token: str | None = None) -> None:
    """Refuse to serve the whole API, code graph included, to the network unauthenticated.

    The token check was request-scoped and guarded by `if token`, so with
    COS_HUB_TOKEN unset and COS_WEB_HOST=0.0.0.0 every route answered anyone who
    could reach the port — and nothing said so at startup. A warning would not
    help: by the time it scrolls past, the port is already open.
    """
    if _is_loopback_bind(host):
        return
    if token if token is not None else _hub_token():
        return
    if os.environ.get("COS_HUB_ALLOW_INSECURE_BIND", "").strip() == "1":
        return
    raise InsecureBindError(
        f"refusing to bind {host!r}: off-loopback with no COS_HUB_TOKEN would expose "
        "the API and the full code graph to the network unauthenticated.\n"
        "  Fix: export COS_HUB_TOKEN=<secret>  (clients send Authorization: Bearer <secret>)\n"
        "  Or:  bind loopback and reverse-proxy with your own auth in front.\n"
        "  Override (you accept the exposure): COS_HUB_ALLOW_INSECURE_BIND=1\n"
        "  Threat model: docs/engineering/hub-threat-model.md"
    )


def _hostname_of_authority(authority: str) -> str:
    """Strip the port from a `host[:port]` authority, unwrapping IPv6 [::1]."""
    authority = authority.strip().lower()
    if authority.startswith("["):  # [::1]:9188 → ::1
        return authority[1:].split("]", 1)[0]
    return authority.rsplit(":", 1)[0] if ":" in authority else authority


def _hostname_of_url(url: str) -> str:
    """Extract the hostname from an Origin/Referer URL (no port, no scheme)."""
    host = urlsplit(url.strip()).hostname
    return (host or "").lower()


def _cors_allow_all() -> bool:
    return os.environ.get("COS_WEB_CORS_ALLOW_ALL", "0").strip() == "1"


def _forbidden(message: str) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={
            "ok": False,
            "error": {"category": "forbidden", "message": message, "retryable": False},
        },
    )


def _unauthorized(message: str) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={
            "ok": False,
            "error": {"category": "unauthorized", "message": message, "retryable": False},
        },
        headers={"WWW-Authenticate": "Bearer"},
    )


def _hub_token() -> str:
    return os.environ.get("COS_HUB_TOKEN", "").strip()


class SecurityGateMiddleware(BaseHTTPMiddleware):
    """Reject cross-origin / DNS-rebinding / CSRF requests on the local hub."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Optional bearer token: when COS_HUB_TOKEN is set, every
        # state-changing API request must carry it — including non-browser
        # clients, and regardless of the CORS dev escape (fail-closed).
        # Default (token unset) keeps open-localhost behavior.
        #
        # Read-route auth: on a NON-loopback host (reverse-proxy /
        # shared box / 0.0.0.0 bind) a read `GET /api/*` exposes the entire
        # code graph, so when the token is set reads require it there too.
        # Loopback (the single-user dev default) keeps reads open and
        # byte-unchanged. Non-loopback = the resolved Host is not in
        # _BASE_ALLOWED_HOSTS. Caveat: a reverse proxy can forge Host /
        # X-Forwarded-* (documented in hub-threat-model.md).
        token = _hub_token()
        method = request.method.upper()
        if token and method != "OPTIONS" and request.url.path.startswith("/api/"):
            host_name = _hostname_of_authority(request.headers.get("host", ""))
            non_loopback = bool(host_name) and host_name not in _BASE_ALLOWED_HOSTS
            if method in _MUTATING_METHODS or non_loopback:
                supplied = request.headers.get("authorization", "")
                if not secrets.compare_digest(supplied, f"Bearer {token}"):
                    return _unauthorized(
                        "COS_HUB_TOKEN is set — pass Authorization: Bearer <token>"
                    )

        if _cors_allow_all():
            return await call_next(request)

        headers = request.headers
        origin = headers.get("origin")
        referer = headers.get("referer")
        allowed = _allowed_hosts()
        is_mutation = method in _MUTATING_METHODS
        is_api = request.url.path.startswith("/api/")

        # The gate engages only on state-changing API requests. Reads are
        # confidentiality-protected by CORS (a cross-origin page cannot read
        # the response), and OPTIONS preflight must pass through untouched.
        if is_mutation and is_api:
            # A browser ALWAYS sends Origin on a state-changing fetch (and at
            # minimum a Referer on a form POST). Absence of both ⇒ a
            # non-browser client (curl / server-to-server / MCP / test), which
            # is not a CSRF/rebinding vector → allow.
            if origin is not None:
                if _hostname_of_url(origin) not in allowed:
                    return _forbidden(f"cross-origin request from {origin!r} rejected")
            elif referer is not None and _hostname_of_url(referer) not in allowed:
                return _forbidden(f"cross-origin referer {referer!r} rejected")

            if origin is not None or referer is not None:
                # DNS-rebinding defense: a rebound page sends the attacker's
                # hostname in Host even when its Origin looks local.
                host_name = _hostname_of_authority(headers.get("host", ""))
                if host_name and host_name not in allowed:
                    return _forbidden(f"host {host_name!r} is not an allowed localhost name")

                # CSRF double-submit: once the cookie has been issued
                # (same-origin production), X-CSRF-Token must echo it.
                cookie_token = request.cookies.get(CSRF_COOKIE)
                if cookie_token is not None and headers.get(CSRF_HEADER) != cookie_token:
                    return _forbidden("missing or mismatched CSRF token")

        response = await call_next(request)

        if CSRF_COOKIE not in request.cookies:
            response.set_cookie(
                CSRF_COOKIE,
                secrets.token_urlsafe(32),
                max_age=7 * 24 * 3600,
                httponly=False,  # double-submit: the SPA must read it
                samesite="lax",
                path="/",
            )
        return response
