"""JWT verification for Supabase Auth (JWKS or legacy HS256) and dev-mode tokens (docs/SECURITY.md §2)."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

import jwt
from jwt import PyJWKClient

from app.core.config import Settings, get_settings
from app.core.errors import Forbidden, Unauthorized

DEV_ISSUER = "careerpilot-dev"
_jwks_client: PyJWKClient | None = None


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    email: str
    claims: dict[str, Any]


def issue_dev_token(email: str, user_id: uuid.UUID | None = None, ttl_seconds: int = 86400, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    if settings.auth_mode != "dev" or settings.app_env == "production":
        raise Forbidden("Dev tokens are disabled.")
    uid = user_id or uuid.uuid5(uuid.NAMESPACE_URL, f"careerpilot-dev:{email.lower()}")
    now = int(time.time())
    payload = {"sub": str(uid), "email": email.lower(), "aud": "authenticated", "iss": DEV_ISSUER,
               "role": "authenticated", "iat": now, "exp": now + ttl_seconds}
    return jwt.encode(payload, settings.dev_auth_secret.get_secret_value(), algorithm="HS256")


def _jwks(settings: Settings) -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(settings.jwks_url, cache_keys=True, lifespan=600)
    return _jwks_client


def verify_token(token: str, settings: Settings | None = None) -> Principal:
    settings = settings or get_settings()
    options = {"require": ["exp", "sub"], "verify_aud": True}
    try:
        header = jwt.get_unverified_header(token)
        alg = header.get("alg")
        if alg in (None, "none"):
            raise Unauthorized("Unsigned tokens are not accepted.")
        if settings.auth_mode == "dev":
            if settings.app_env == "production":
                raise Unauthorized("Dev auth is disabled in production.")
            claims = jwt.decode(token, settings.dev_auth_secret.get_secret_value(), algorithms=["HS256"],
                                audience="authenticated", issuer=DEV_ISSUER, options=options, leeway=30)
        elif alg == "HS256":
            if not settings.supabase_jwt_secret:
                raise Unauthorized("HS256 tokens are not accepted by this deployment.")
            claims = jwt.decode(token, settings.supabase_jwt_secret.get_secret_value(), algorithms=["HS256"],
                                audience=settings.supabase_jwt_audience, issuer=settings.jwt_issuer or None,
                                options=options, leeway=30)
        else:
            key = _jwks(settings).get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256", "ES256", "EdDSA"],
                                audience=settings.supabase_jwt_audience, issuer=settings.jwt_issuer or None,
                                options=options, leeway=30)
    except Unauthorized:
        raise
    except jwt.PyJWTError as exc:
        raise Unauthorized("Invalid or expired token.") from exc
    try:
        user_id = uuid.UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise Unauthorized("Token subject is not a user id.") from exc
    email = str(claims.get("email") or "").lower()
    if settings.allowed_emails and email not in settings.allowed_emails:
        raise Forbidden()
    return Principal(user_id=user_id, email=email, claims=claims)
