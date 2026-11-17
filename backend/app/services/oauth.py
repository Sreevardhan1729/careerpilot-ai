"""Google OAuth connection lifecycle: state+PKCE, encrypted tokens, refresh, revoke (spec §4.4)."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app.core import crypto
from app.core.config import get_settings
from app.core.db import system_session, user_session
from app.core.errors import IntegrationNotConnected, NotFound, UpstreamError
from app.integrations import gmail
from app.models import OAuthConnection, OAuthState
from app.services.common import audit
from app.services.notifications import notify


async def authorize_url(user_id: uuid.UUID) -> str:
    crypto._keys()  # fail fast if token encryption is not configured
    verifier, challenge = gmail.new_pkce()
    state = secrets.token_urlsafe(32)
    async with system_session() as s:
        await s.execute(delete(OAuthState).where(OAuthState.expires_at < datetime.now(tz=UTC)))
        s.add(OAuthState(state=state, user_id=user_id, provider="google", code_verifier=verifier,
                         expires_at=datetime.now(tz=UTC) + timedelta(minutes=10)))
    return gmail.authorize_url(state, challenge)


async def callback(code: str, state: str) -> uuid.UUID:
    async with system_session() as s:
        row = await s.get(OAuthState, state)
        if row is None or row.expires_at < datetime.now(tz=UTC):
            raise NotFound("This sign-in link expired. Start the Google connection again.")
        user_id, verifier = row.user_id, row.code_verifier
        await s.delete(row)
    tokens = await gmail.exchange_code(code, verifier)
    access, refresh = tokens.get("access_token"), tokens.get("refresh_token")
    if not access:
        raise UpstreamError("Google did not return an access token.")
    email = await gmail.userinfo_email(access)
    acc_enc, key_id = crypto.encrypt(access)
    ref_enc = crypto.encrypt(refresh)[0] if refresh else None
    async with user_session(user_id) as s:
        conn = (await s.execute(select(OAuthConnection).where(OAuthConnection.user_id == user_id,
                                                              OAuthConnection.provider == "google"))).scalar_one_or_none()
        if conn is None:
            conn = OAuthConnection(user_id=user_id, provider="google", token_key_id=key_id, status="active")
            s.add(conn)
        conn.access_token_enc, conn.token_key_id, conn.status = acc_enc, key_id, "active"
        conn.refresh_token_enc = ref_enc or conn.refresh_token_enc
        conn.scopes = (tokens.get("scope") or " ".join(gmail.SCOPES)).split()
        conn.account_email = email
        conn.expires_at = datetime.now(tz=UTC) + timedelta(seconds=int(tokens.get("expires_in", 3600)))
        await audit(s, user_id, "oauth.connected", "oauth_connection", conn.id, provider="google")
    return user_id


async def access_token(user_id: uuid.UUID) -> tuple[str, str | None]:
    """Return (access_token, account_email), refreshing if needed. Tokens never leave the server."""
    async with user_session(user_id) as s:
        conn = (await s.execute(select(OAuthConnection).where(OAuthConnection.user_id == user_id,
                                                              OAuthConnection.provider == "google"))).scalar_one_or_none()
        if conn is None or conn.status != "active" or conn.access_token_enc is None:
            raise IntegrationNotConnected("Connect Google in Settings → Integrations first.")
        if conn.expires_at and conn.expires_at > datetime.now(tz=UTC) + timedelta(minutes=2):
            await audit(s, user_id, "oauth.token_used", "oauth_connection", conn.id)
            return crypto.decrypt(conn.access_token_enc), conn.account_email
        if conn.refresh_token_enc is None:
            conn.status = "expired"
            raise IntegrationNotConnected("Google authorisation expired. Reconnect Google.")
        try:
            tokens = await gmail.refresh(crypto.decrypt(conn.refresh_token_enc))
        except UpstreamError:
            conn.status = "expired"
            await notify(user_id, "reconnect_google", "Reconnect Google",
                         "Google authorisation expired (Testing-mode apps expire every 7 days).", "/settings?tab=integrations")
            raise IntegrationNotConnected("Google authorisation expired. Reconnect Google.") from None
        conn.access_token_enc, conn.token_key_id = crypto.encrypt(tokens["access_token"])
        conn.expires_at = datetime.now(tz=UTC) + timedelta(seconds=int(tokens.get("expires_in", 3600)))
        await audit(s, user_id, "oauth.token_refreshed", "oauth_connection", conn.id)
        return tokens["access_token"], conn.account_email


async def disconnect(user_id: uuid.UUID) -> None:
    async with user_session(user_id) as s:
        conn = (await s.execute(select(OAuthConnection).where(OAuthConnection.user_id == user_id,
                                                              OAuthConnection.provider == "google"))).scalar_one_or_none()
        if conn is None:
            return
        token = None
        try:
            enc = conn.refresh_token_enc or conn.access_token_enc
            token = crypto.decrypt(enc) if enc else None
        except Exception:
            token = None
        await s.delete(conn)
        await audit(s, user_id, "oauth.disconnected", "oauth_connection", conn.id, provider="google")
    if token:
        try:
            await gmail.revoke(token)
        except Exception:
            pass


def frontend_redirect(status: str) -> str:
    return get_settings().frontend_origin.rstrip("/") + f"/settings?tab=integrations&google={status}"
