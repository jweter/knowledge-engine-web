"""Optional HTTP Basic Auth gate for an unlisted alpha deployment.

Off by default -- only activates when both `KE_WEB_ALPHA_USERNAME` and
`KE_WEB_ALPHA_PASSWORD` are configured. This is a stopgap for a small,
password-shared alpha test, not a real authentication system -- see
`docs/deployment.md`'s "Alpha access" section. Real multi-user
authentication stays deferred per `docs/web_design.md`'s Out of Scope
until there is an actual design for it.
"""

from __future__ import annotations

import base64
import secrets

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from knowledge_engine_web.config import Settings


class AlphaBasicAuthMiddleware(BaseHTTPMiddleware):
    """Require HTTP Basic Auth when alpha credentials are configured.

    Reads `Settings()` fresh on every request -- matching this
    project's existing per-request settings pattern (`_engine()`,
    `read_evidence_record`) -- rather than baking credentials in at
    app-startup time, so the gate is testable the same way every other
    route already is, and toggling the env vars takes effect
    immediately with no restart.

    If exactly one of the two settings is configured (a misconfiguration,
    not "intentionally open"), this fails closed -- every request is
    denied -- rather than silently leaving the alpha unprotected.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        settings = Settings()
        username = settings.alpha_username
        password = settings.alpha_password

        if username is None and password is None:
            return await call_next(request)

        if username is None or password is None:
            return Response(
                "Alpha auth misconfigured: KE_WEB_ALPHA_USERNAME and "
                "KE_WEB_ALPHA_PASSWORD must both be set together.",
                status_code=500,
            )

        header = request.headers.get("authorization")
        if header and _credentials_match(header, username, password):
            return await call_next(request)

        return Response(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Knowledge Engine alpha"'},
        )


def _credentials_match(header: str, expected_username: str, expected_password: str) -> bool:
    scheme, _, encoded = header.partition(" ")
    if scheme.lower() != "basic" or not encoded:
        return False
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False
    username, _, password = decoded.partition(":")
    return secrets.compare_digest(username, expected_username) and secrets.compare_digest(
        password, expected_password
    )
