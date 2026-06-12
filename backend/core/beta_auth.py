import base64
import binascii
import secrets
from collections.abc import Iterable

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

CHALLENGE = 'Basic realm="CapiLearn Beta"'


class BetaAuthMiddleware:
    """Temporary backend gate until Clerk authentication is enabled end-to-end."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        username: str,
        password: str,
        public_paths: Iterable[str] = ("/health",),
    ) -> None:
        self.app = app
        self.username = username.encode("utf-8")
        self.password = password.encode("utf-8")
        self.public_paths = frozenset(public_paths)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] == "OPTIONS"
            or scope["path"] in self.public_paths
        ):
            await self.app(scope, receive, send)
            return

        credentials = self._parse_credentials(Headers(scope=scope).get("authorization"))
        if credentials is None or not self._credentials_match(*credentials):
            response = JSONResponse(
                {"detail": "Unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": CHALLENGE},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

    @staticmethod
    def _parse_credentials(authorization: str | None) -> tuple[bytes, bytes] | None:
        if not authorization:
            return None

        scheme, _, encoded = authorization.partition(" ")
        if scheme.lower() != "basic" or not encoded:
            return None

        try:
            decoded = base64.b64decode(encoded, validate=True)
            username, separator, password = decoded.partition(b":")
        except (binascii.Error, ValueError):
            return None

        if not separator:
            return None
        return username, password

    def _credentials_match(self, username: bytes, password: bytes) -> bool:
        username_matches = secrets.compare_digest(username, self.username)
        password_matches = secrets.compare_digest(password, self.password)
        return username_matches & password_matches
