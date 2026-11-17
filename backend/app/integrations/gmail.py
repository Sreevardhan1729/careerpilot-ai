"""Google OAuth (PKCE, gmail.compose only) and Gmail draft/send calls (spec §4.4; docs/SECURITY.md §8)."""

from __future__ import annotations

import base64
import hashlib
import secrets
from email.message import EmailMessage
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings
from app.core.errors import IntegrationNotConnected, UpstreamError

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
SCOPES = ["openid", "email", "https://www.googleapis.com/auth/gmail.compose"]


def redirect_uri() -> str:
    return get_settings().backend_public_url.rstrip("/") + "/api/v1/integrations/google/callback"


def _client() -> tuple[str, str]:
    s = get_settings()
    if not (s.google_oauth_client_id and s.google_oauth_client_secret):
        raise IntegrationNotConnected("Google OAuth is not configured on this deployment.")
    return s.google_oauth_client_id, s.google_oauth_client_secret.get_secret_value()


def new_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def authorize_url(state: str, code_challenge: str) -> str:
    client_id, _ = _client()
    return AUTH_URL + "?" + urlencode({
        "client_id": client_id, "redirect_uri": redirect_uri(), "response_type": "code", "scope": " ".join(SCOPES),
        "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true", "state": state,
        "code_challenge": code_challenge, "code_challenge_method": "S256",
    })


async def _post(url: str, data: dict) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(url, data=data)
    if resp.status_code >= 400:
        raise UpstreamError("Google OAuth request failed.", details={"status": resp.status_code})
    return resp.json()


async def exchange_code(code: str, verifier: str) -> dict:
    client_id, secret = _client()
    return await _post(TOKEN_URL, {"code": code, "client_id": client_id, "client_secret": secret,
                                   "redirect_uri": redirect_uri(), "grant_type": "authorization_code", "code_verifier": verifier})


async def refresh(refresh_token: str) -> dict:
    client_id, secret = _client()
    return await _post(TOKEN_URL, {"refresh_token": refresh_token, "client_id": client_id, "client_secret": secret,
                                   "grant_type": "refresh_token"})


async def userinfo_email(access_token: str) -> str | None:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
    return resp.json().get("email") if resp.status_code == 200 else None


async def revoke(token: str) -> None:
    async with httpx.AsyncClient(timeout=15) as client:
        await client.post(REVOKE_URL, data={"token": token})  # body, not query string (keeps it out of access logs)


def _raw(to: str | None, subject: str, body: str, sender: str | None) -> str:
    msg = EmailMessage()
    if to:
        msg["To"] = to
    if sender:
        msg["From"] = sender
    msg["Subject"] = subject
    msg.set_content(body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


async def _gmail(method: str, path: str, token: str, json: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(method, GMAIL + path, headers={"Authorization": f"Bearer {token}"}, json=json)
    except httpx.HTTPError as exc:  # includes timeouts: the outcome of a send is then unknown
        raise UpstreamError("Gmail did not respond.", details={"error": type(exc).__name__}) from exc
    if resp.status_code == 401:
        raise IntegrationNotConnected("Google authorisation expired. Reconnect Google in Settings.")
    if resp.status_code >= 400:
        raise UpstreamError("Gmail request failed.", details={"status": resp.status_code})
    return resp.json()


async def create_draft(token: str, to: str | None, subject: str, body: str, sender: str | None) -> str:
    data = await _gmail("POST", "/drafts", token, {"message": {"raw": _raw(to, subject, body, sender)}})
    return data["id"]


async def send_message(token: str, to: str, subject: str, body: str, sender: str | None) -> str:
    data = await _gmail("POST", "/messages/send", token, {"raw": _raw(to, subject, body, sender)})
    return data["id"]
