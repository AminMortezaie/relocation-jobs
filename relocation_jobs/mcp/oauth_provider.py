from __future__ import annotations

import os
from urllib.parse import urlencode

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from relocation_jobs.mcp import oauth_repo


def public_base_url() -> str:
    return (os.environ.get("MCP_PUBLIC_BASE_URL") or "http://127.0.0.1:10001").rstrip("/")


def panel_display_base_url() -> str:
    raw = (os.environ.get("MCP_PUBLIC_BASE_URL") or "").strip()
    if raw:
        return raw.rstrip("/")
    return "https://mcp.kuchup.com"


def mcp_resource_url() -> str:
    return f"{public_base_url()}/mcp"


class KuchupOAuthProvider(OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]):
    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return oauth_repo.get_client(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        oauth_repo.save_client(client_info)

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        request_id = oauth_repo.create_pending_request(
            client.client_id,
            {
                "state": params.state,
                "scopes": params.scopes or [],
                "code_challenge": params.code_challenge,
                "redirect_uri": str(params.redirect_uri),
                "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
                "resource": params.resource,
            },
        )
        return f"{public_base_url()}/oauth/login?{urlencode({'request_id': request_id})}"

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        return oauth_repo.load_authorization_code(client.client_id, authorization_code)

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        if authorization_code.subject is None:
            raise TokenError(error="invalid_grant", error_description="Missing subject")
        user_id = int(authorization_code.subject)
        oauth_repo.consume_authorization_code(authorization_code.code)
        access, refresh, expires_in = oauth_repo.issue_token_pair(
            client_id=client.client_id,
            user_id=user_id,
            scopes=authorization_code.scopes,
            resource=authorization_code.resource,
        )
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=expires_in,
            scope=" ".join(authorization_code.scopes) if authorization_code.scopes else None,
            refresh_token=refresh,
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        return oauth_repo.load_refresh_token(client.client_id, refresh_token)

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        if refresh_token.subject is None:
            raise TokenError(error="invalid_grant", error_description="Missing subject")
        user_id = int(refresh_token.subject)
        oauth_repo.revoke_token_raw(refresh_token.token)
        next_scopes = scopes or refresh_token.scopes
        access, refresh, expires_in = oauth_repo.issue_token_pair(
            client_id=client.client_id,
            user_id=user_id,
            scopes=next_scopes,
            resource=None,
        )
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=expires_in,
            scope=" ".join(next_scopes) if next_scopes else None,
            refresh_token=refresh,
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        api = oauth_repo.resolve_api_token(token)
        if api is not None:
            return api
        return oauth_repo.load_access_token(token)

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        oauth_repo.revoke_token_raw(token.token)


def complete_login_redirect(*, request_id: str, user_id: int) -> str:
    pending = oauth_repo.get_pending_request(request_id)
    if pending is None:
        raise AuthorizeError(error="invalid_request", error_description="Authorization request expired")
    client = oauth_repo.get_client(pending["client_id"])
    if client is None:
        raise AuthorizeError(error="unauthorized_client", error_description="Unknown client")
    params = pending["params"]
    scopes = params.get("scopes") or ["mcp"]
    code = oauth_repo.issue_authorization_code(
        client_id=client.client_id,
        user_id=user_id,
        scopes=scopes,
        code_challenge=params["code_challenge"],
        redirect_uri=params["redirect_uri"],
        redirect_uri_provided_explicitly=bool(params.get("redirect_uri_provided_explicitly")),
        resource=params.get("resource"),
    )
    oauth_repo.delete_pending_request(request_id)
    return construct_redirect_uri(
        params["redirect_uri"],
        code=code,
        state=params.get("state"),
    )
