"""Dhan session: exchange client ID + PIN + daily TOTP for a 24-hour access token.

DHAN_CLIENT_ID and DHAN_PIN live in the environment (.env). The TOTP is typed by the user once a day
and never stored. The resulting token is kept in idt/dhan_token.json (mode 0600) until it expires.
DHAN_ACCESS_TOKEN, if set, overrides the stored token (manual token from web.dhan.co).
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta

import requests

from ..config import workspace
from ..market import IST, now_ist
from .base import DataError

AUTH_URL = "https://auth.dhan.co/app/generateAccessToken"
TOKEN_FILE = "dhan_token.json"
EXPIRY_MARGIN = timedelta(minutes=5)       # treat a token as expired slightly early
MIN_LOGIN_INTERVAL = 5.0                   # seconds between attempts (Dhan may lock repeated failures)
_last_attempt = 0.0


def _path():
    return workspace() / TOKEN_FILE


def _parse_expiry(value) -> datetime:
    """Dhan returns expiryTime as an IST timestamp; fall back to now + 24h if it can't be parsed."""
    if value:
        text = str(value).strip().replace("Z", "+00:00")
        for parse in (datetime.fromisoformat, lambda s: datetime.strptime(s, "%Y-%m-%d %H:%M:%S")):
            try:
                dt = parse(text)
                return dt if dt.tzinfo else dt.replace(tzinfo=IST)
            except ValueError:
                continue
        if text.isdigit():  # epoch seconds or milliseconds
            n = int(text)
            return datetime.fromtimestamp(n / 1000 if n > 1e11 else n, IST)
    return now_ist() + timedelta(hours=24)


def load_session() -> dict | None:
    path = _path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        data["expires_at"] = datetime.fromisoformat(data["expires_at"])
        return data
    except (ValueError, KeyError):
        return None


def save_session(client_id: str, token: str, expires_at: datetime, client_name: str | None = None) -> None:
    path = _path()
    payload = {"client_id": client_id, "access_token": token, "expires_at": expires_at.isoformat(),
               "client_name": client_name, "created_at": now_ist().isoformat()}
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(payload, fh)
    os.chmod(path, 0o600)


def clear_session() -> None:
    _path().unlink(missing_ok=True)


def current_credentials(now: datetime | None = None) -> tuple[str, str] | None:
    """(client_id, access_token) to use for API calls, or None if there is no valid session."""
    client_id = os.environ.get("DHAN_CLIENT_ID", "")
    manual = os.environ.get("DHAN_ACCESS_TOKEN", "")
    if client_id and manual:
        return client_id, manual
    s = load_session()
    if s and s["expires_at"] - EXPIRY_MARGIN > (now or now_ist()):
        return s["client_id"], s["access_token"]
    return None


def status(now: datetime | None = None) -> dict:
    now = now or now_ist()
    client_id = os.environ.get("DHAN_CLIENT_ID", "")
    has_pin = bool(os.environ.get("DHAN_PIN"))
    out = {"client_id_set": bool(client_id), "pin_set": has_pin, "totp_login_available": bool(client_id and has_pin)}
    if client_id and os.environ.get("DHAN_ACCESS_TOKEN"):
        return dict(out, connected=True, source="env", expires_at=None, expires_in_seconds=None,
                    message="Using DHAN_ACCESS_TOKEN from the environment.")
    s = load_session()
    if s and s["expires_at"] - EXPIRY_MARGIN > now:
        left = int((s["expires_at"] - now).total_seconds())
        return dict(out, connected=True, source="totp", client_name=s.get("client_name"),
                    expires_at=s["expires_at"].isoformat(), expires_in_seconds=left,
                    message=f"Dhan session active for {left // 3600}h {left % 3600 // 60}m.")
    if s:
        msg = "Dhan session expired. Enter today's TOTP to reconnect."
    elif out["totp_login_available"]:
        msg = "Not connected. Enter the 6-digit TOTP from your authenticator app."
    else:
        msg = "Set DHAN_CLIENT_ID and DHAN_PIN in .env, then enter your TOTP."
    return dict(out, connected=False, source=None, expires_at=s["expires_at"].isoformat() if s else None,
                expires_in_seconds=0 if s else None, message=msg)


def login(totp: str, session: requests.Session | None = None, now: datetime | None = None) -> dict:
    """Exchange the TOTP for a token. Raises DataError with a user-facing message on failure."""
    global _last_attempt
    totp = (totp or "").strip()
    if not re.fullmatch(r"\d{6}", totp):
        raise DataError("TOTP must be the 6-digit code from your authenticator app.")
    client_id = os.environ.get("DHAN_CLIENT_ID", "")
    pin = os.environ.get("DHAN_PIN", "")
    if not (client_id and pin):
        raise DataError("Set DHAN_CLIENT_ID and DHAN_PIN in .env (then restart the server) before logging in with TOTP.")
    wait = MIN_LOGIN_INTERVAL - (time.monotonic() - _last_attempt)
    if wait > 0:
        raise DataError(f"Please wait {wait:.0f}s before trying again.")
    _last_attempt = time.monotonic()

    try:
        resp = (session or requests).post(AUTH_URL, params={"dhanClientId": client_id, "pin": pin, "totp": totp}, timeout=20)
    except requests.RequestException as exc:
        raise DataError(f"Could not reach Dhan: {exc}") from exc
    try:
        body = resp.json()
    except ValueError:
        body = {}
    token = body.get("accessToken") if isinstance(body, dict) else None
    if resp.status_code != 200 or not token:
        reason = (body.get("errorMessage") or body.get("message") or body.get("error")) if isinstance(body, dict) else None
        raise DataError("Dhan rejected the login: " + (reason or f"HTTP {resp.status_code}")
                        + ". Check the TOTP (codes change every 30s), your PIN, and that TOTP is enabled on web.dhan.co.")
    expires_at = _parse_expiry(body.get("expiryTime"))
    save_session(str(body.get("dhanClientId") or client_id), token, expires_at, body.get("dhanClientName"))
    return status(now)
