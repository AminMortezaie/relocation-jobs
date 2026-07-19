from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone

from mcp.server.auth.provider import AccessToken, AuthorizationCode, RefreshToken
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl

from relocation_jobs.core.db import _utc_now, db_read, db_transaction

PENDING_TTL_SECONDS = 900
AUTH_CODE_TTL_SECONDS = 600
ACCESS_TOKEN_TTL_SECONDS = 3600
REFRESH_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 30
API_TOKEN_PREFIX = "kch_"
ACCESS_TOKEN_PREFIX = "mcp_at_"
REFRESH_TOKEN_PREFIX = "mcp_rt_"
AUTH_CODE_PREFIX = "mcp_ac_"


def hash_secret(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _is_expired(expires_at: str | None) -> bool:
    when = _parse_iso(expires_at)
    if when is None:
        return False
    now = datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when <= now


def _row(row) -> dict:
    return dict(row) if row else {}


def save_client(client_info: OAuthClientInformationFull) -> None:
    now = _utc_now()
    payload = client_info.model_dump_json()
    with db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO mcp_oauth_clients (client_id, client_info_json, created_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (client_id) DO UPDATE SET client_info_json = EXCLUDED.client_info_json
            """,
            (client_info.client_id, payload, now),
        )


def get_client(client_id: str) -> OAuthClientInformationFull | None:
    with db_read() as conn:
        row = conn.execute(
            "SELECT client_info_json FROM mcp_oauth_clients WHERE client_id = %s",
            (client_id,),
        ).fetchone()
    if not row:
        return None
    return OAuthClientInformationFull.model_validate_json(row["client_info_json"])


def create_pending_request(client_id: str, params: dict) -> str:
    request_id = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    expires = (now + timedelta(seconds=PENDING_TTL_SECONDS)).isoformat()
    with db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO mcp_oauth_pending (request_id, client_id, params_json, expires_at, created_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (request_id, client_id, json.dumps(params), expires, now.isoformat()),
        )
    return request_id


def get_pending_request(request_id: str) -> dict | None:
    with db_read() as conn:
        row = conn.execute(
            """
            SELECT request_id, client_id, params_json, expires_at
            FROM mcp_oauth_pending
            WHERE request_id = %s
            """,
            (request_id,),
        ).fetchone()
    data = _row(row)
    if not data or _is_expired(data.get("expires_at")):
        return None
    data["params"] = json.loads(data["params_json"])
    return data


def delete_pending_request(request_id: str) -> None:
    with db_transaction() as conn:
        conn.execute("DELETE FROM mcp_oauth_pending WHERE request_id = %s", (request_id,))


def issue_authorization_code(
    *,
    client_id: str,
    user_id: int,
    scopes: list[str],
    code_challenge: str,
    redirect_uri: str,
    redirect_uri_provided_explicitly: bool,
    resource: str | None,
) -> str:
    code = AUTH_CODE_PREFIX + secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires = (now + timedelta(seconds=AUTH_CODE_TTL_SECONDS)).isoformat()
    with db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO mcp_oauth_auth_codes (
                code_hash, client_id, user_id, scopes_json, code_challenge,
                redirect_uri, redirect_uri_provided_explicitly, resource,
                expires_at, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                hash_secret(code),
                client_id,
                user_id,
                json.dumps(scopes),
                code_challenge,
                redirect_uri,
                1 if redirect_uri_provided_explicitly else 0,
                resource,
                expires,
                now.isoformat(),
            ),
        )
    return code


def load_authorization_code(client_id: str, code: str) -> AuthorizationCode | None:
    with db_read() as conn:
        row = conn.execute(
            """
            SELECT code_hash, client_id, user_id, scopes_json, code_challenge,
                   redirect_uri, redirect_uri_provided_explicitly, resource,
                   expires_at, consumed_at
            FROM mcp_oauth_auth_codes
            WHERE code_hash = %s AND client_id = %s
            """,
            (hash_secret(code), client_id),
        ).fetchone()
    data = _row(row)
    if not data or data.get("consumed_at") or _is_expired(data.get("expires_at")):
        return None
    expires_at = _parse_iso(data["expires_at"])
    assert expires_at is not None
    return AuthorizationCode(
        code=code,
        client_id=client_id,
        scopes=json.loads(data["scopes_json"]),
        expires_at=expires_at.timestamp(),
        code_challenge=data["code_challenge"],
        redirect_uri=AnyUrl(data["redirect_uri"]),
        redirect_uri_provided_explicitly=bool(data["redirect_uri_provided_explicitly"]),
        resource=data.get("resource"),
        subject=str(data["user_id"]),
    )


def consume_authorization_code(code: str) -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            UPDATE mcp_oauth_auth_codes
            SET consumed_at = %s
            WHERE code_hash = %s
            """,
            (_utc_now(), hash_secret(code)),
        )


def _store_token(
    *,
    raw: str,
    kind: str,
    client_id: str,
    user_id: int,
    scopes: list[str],
    resource: str | None,
    expires_at: str | None,
) -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO mcp_oauth_tokens (
                token_hash, token_kind, client_id, user_id, scopes_json,
                resource, expires_at, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                hash_secret(raw),
                kind,
                client_id,
                user_id,
                json.dumps(scopes),
                resource,
                expires_at,
                _utc_now(),
            ),
        )


def issue_token_pair(
    *,
    client_id: str,
    user_id: int,
    scopes: list[str],
    resource: str | None,
) -> tuple[str, str, int]:
    access = ACCESS_TOKEN_PREFIX + secrets.token_urlsafe(32)
    refresh = REFRESH_TOKEN_PREFIX + secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    access_exp = (now + timedelta(seconds=ACCESS_TOKEN_TTL_SECONDS)).isoformat()
    refresh_exp = (now + timedelta(seconds=REFRESH_TOKEN_TTL_SECONDS)).isoformat()
    _store_token(
        raw=access,
        kind="access",
        client_id=client_id,
        user_id=user_id,
        scopes=scopes,
        resource=resource,
        expires_at=access_exp,
    )
    _store_token(
        raw=refresh,
        kind="refresh",
        client_id=client_id,
        user_id=user_id,
        scopes=scopes,
        resource=resource,
        expires_at=refresh_exp,
    )
    return access, refresh, ACCESS_TOKEN_TTL_SECONDS


def load_access_token(token: str) -> AccessToken | None:
    with db_read() as conn:
        row = conn.execute(
            """
            SELECT token_hash, client_id, user_id, scopes_json, resource, expires_at, revoked_at
            FROM mcp_oauth_tokens
            WHERE token_hash = %s AND token_kind = 'access'
            """,
            (hash_secret(token),),
        ).fetchone()
    data = _row(row)
    if not data or data.get("revoked_at") or _is_expired(data.get("expires_at")):
        return None
    expires = _parse_iso(data.get("expires_at"))
    return AccessToken(
        token=token,
        client_id=data["client_id"],
        scopes=json.loads(data["scopes_json"]),
        expires_at=int(expires.timestamp()) if expires else None,
        resource=data.get("resource"),
        subject=str(data["user_id"]),
    )


def load_refresh_token(client_id: str, token: str) -> RefreshToken | None:
    with db_read() as conn:
        row = conn.execute(
            """
            SELECT token_hash, client_id, user_id, scopes_json, expires_at, revoked_at
            FROM mcp_oauth_tokens
            WHERE token_hash = %s AND token_kind = 'refresh' AND client_id = %s
            """,
            (hash_secret(token), client_id),
        ).fetchone()
    data = _row(row)
    if not data or data.get("revoked_at") or _is_expired(data.get("expires_at")):
        return None
    expires = _parse_iso(data.get("expires_at"))
    return RefreshToken(
        token=token,
        client_id=client_id,
        scopes=json.loads(data["scopes_json"]),
        expires_at=int(expires.timestamp()) if expires else None,
        subject=str(data["user_id"]),
    )


def revoke_token_raw(token: str) -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            UPDATE mcp_oauth_tokens
            SET revoked_at = %s
            WHERE token_hash = %s AND revoked_at IS NULL
            """,
            (_utc_now(), hash_secret(token)),
        )


def create_api_token(*, user_id: int, label: str = "") -> tuple[int, str]:
    raw = API_TOKEN_PREFIX + secrets.token_urlsafe(32)
    now = _utc_now()
    with db_transaction() as conn:
        row = conn.execute(
            """
            INSERT INTO mcp_api_tokens (user_id, token_hash, label, created_at)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (user_id, hash_secret(raw), (label or "").strip(), now),
        ).fetchone()
    return int(row["id"]), raw


def list_api_tokens(user_id: int) -> list[dict]:
    with db_read() as conn:
        rows = conn.execute(
            """
            SELECT id, label, created_at, last_used_at, revoked_at
            FROM mcp_api_tokens
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (user_id,),
        ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "label": row["label"] or "",
            "created_at": row["created_at"],
            "last_used_at": row["last_used_at"],
            "revoked": bool(row["revoked_at"]),
        }
        for row in rows
    ]


def revoke_api_token(*, user_id: int, token_id: int) -> bool:
    with db_transaction() as conn:
        cur = conn.execute(
            """
            UPDATE mcp_api_tokens
            SET revoked_at = %s
            WHERE id = %s AND user_id = %s AND revoked_at IS NULL
            """,
            (_utc_now(), token_id, user_id),
        )
        return cur.rowcount > 0


def resolve_api_token(raw: str) -> AccessToken | None:
    if not raw.startswith(API_TOKEN_PREFIX):
        return None
    with db_transaction() as conn:
        row = conn.execute(
            """
            SELECT id, user_id, revoked_at
            FROM mcp_api_tokens
            WHERE token_hash = %s
            """,
            (hash_secret(raw),),
        ).fetchone()
        data = _row(row)
        if not data or data.get("revoked_at"):
            return None
        conn.execute(
            """
            UPDATE mcp_api_tokens
            SET last_used_at = %s
            WHERE id = %s
            """,
            (_utc_now(), data["id"]),
        )
    return AccessToken(
        token=raw,
        client_id="api_token",
        scopes=["mcp"],
        expires_at=None,
        subject=str(data["user_id"]),
    )
