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


class SecurityGateMiddleware(BaseHTTPMiddleware):
    """Reject cross-origin / DNS-rebinding / CSRF requests on the local hub."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if _cors_allow_all():
            return await call_next(request)

        headers = request.headers
        origin = headers.get("origin")
        referer = headers.get("referer")
        allowed = _allowed_hosts()
        method = request.method.upper()
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
            elif referer is not None:
                if _hostname_of_url(referer) not in allowed:
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
