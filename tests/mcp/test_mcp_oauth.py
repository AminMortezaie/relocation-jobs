from __future__ import annotations

import os

import pytest
from mcp.server.auth.provider import AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl

from relocation_jobs.mcp import oauth_repo
from relocation_jobs.mcp import service
from relocation_jobs.mcp.context import reset_current_user_id, set_current_user_id
from relocation_jobs.mcp.oauth_provider import KuchupOAuthProvider, complete_login_redirect
from relocation_jobs.mcp.types import ApplicationProfile
from relocation_jobs.users.repo import create_user
from tests.helpers.passwords import hash_test_password


@pytest.fixture
def two_users(db):
    from relocation_jobs.users.repo import get_user_by_username

    admin = get_user_by_username("admin")
    if admin is None:
        admin = create_user("admin", hash_test_password("adminpass123"))
    other = get_user_by_username("other")
    if other is None:
        other = create_user("other", hash_test_password("otherpass123"))
    service.save_application_profile(
        ApplicationProfile(full_name="Admin Person"),
        user_id=int(admin["id"]),
    )
    service.save_application_profile(
        ApplicationProfile(full_name="Other Person"),
        user_id=int(other["id"]),
    )
    return int(admin["id"]), int(other["id"])


@pytest.mark.asyncio
async def test_oauth_authorize_login_token_scopes_user(two_users):
    admin_id, _other_id = two_users
    provider = KuchupOAuthProvider()
    client = OAuthClientInformationFull(
        client_id="test-client",
        client_secret=None,
        redirect_uris=[AnyUrl("http://localhost:8787/callback")],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method="none",
        scope="mcp",
    )
    await provider.register_client(client)

    login_url = await provider.authorize(
        client,
        AuthorizationParams(
            state="xyz",
            scopes=["mcp"],
            code_challenge="abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
            redirect_uri=AnyUrl("http://localhost:8787/callback"),
            redirect_uri_provided_explicitly=True,
            resource="http://127.0.0.1:10001/mcp",
        ),
    )
    assert "/oauth/login?request_id=" in login_url
    request_id = login_url.rsplit("request_id=", 1)[1]

    redirect = complete_login_redirect(request_id=request_id, user_id=admin_id)
    assert "code=" in redirect
    assert "state=xyz" in redirect
    code = redirect.split("code=")[1].split("&")[0]

    loaded = await provider.load_authorization_code(client, code)
    assert loaded is not None
    assert loaded.subject == str(admin_id)

    token = await provider.exchange_authorization_code(client, loaded)
    assert token.access_token.startswith("mcp_at_")
    assert token.refresh_token.startswith("mcp_rt_")

    access = await provider.load_access_token(token.access_token)
    assert access is not None
    assert access.subject == str(admin_id)
    assert "mcp" in access.scopes


def test_resolve_user_id_prefers_context_over_env(two_users):
    admin_id, other_id = two_users
    os.environ["MCP_USERNAME"] = "admin"
    token = set_current_user_id(other_id)
    try:
        assert service.resolve_user_id() == other_id
    finally:
        reset_current_user_id(token)
    assert service.resolve_user_id() == admin_id


def test_api_token_isolates_users(two_users):
    admin_id, other_id = two_users
    _tid, raw = oauth_repo.create_api_token(user_id=admin_id, label="scripts")
    access = oauth_repo.resolve_api_token(raw)
    assert access is not None
    assert access.subject == str(admin_id)

    listed = oauth_repo.list_api_tokens(admin_id)
    assert len(listed) == 1
    assert listed[0]["label"] == "scripts"
    assert oauth_repo.list_api_tokens(other_id) == []

    assert oauth_repo.revoke_api_token(user_id=other_id, token_id=listed[0]["id"]) is False
    assert oauth_repo.revoke_api_token(user_id=admin_id, token_id=listed[0]["id"]) is True
    assert oauth_repo.resolve_api_token(raw) is None


def test_masters_isolated_by_user(two_users):
    admin_id, other_id = two_users
    service.save_master_resume("go", "\\documentclass{article}\\begin{document}A\\end{document}", label="Admin Go", user_id=admin_id)
    service.save_master_resume("go", "\\documentclass{article}\\begin{document}B\\end{document}", label="Other Go", user_id=other_id)
    admin_masters = service.list_master_resumes(user_id=admin_id)
    other_masters = service.list_master_resumes(user_id=other_id)
    assert [m.label for m in admin_masters] == ["Admin Go"]
    assert [m.label for m in other_masters] == ["Other Go"]
