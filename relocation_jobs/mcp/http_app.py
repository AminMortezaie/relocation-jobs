from __future__ import annotations

import os

from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.fastmcp import FastMCP
from pydantic import AnyHttpUrl
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

from relocation_jobs.mcp.oauth_pages import oauth_health, oauth_login_get, oauth_login_post
from relocation_jobs.mcp.oauth_provider import KuchupOAuthProvider, mcp_resource_url, public_base_url
from relocation_jobs.mcp.server import mcp as stdio_mcp


async def _oauth_login(request: Request) -> HTMLResponse | RedirectResponse:
    if request.method == "GET":
        return await oauth_login_get(request)
    return await oauth_login_post(request)


def _copy_tools(source: FastMCP, dest: FastMCP) -> None:
    for tool in source._tool_manager.list_tools():
        dest.add_tool(
            tool.fn,
            name=tool.name,
            title=tool.title,
            description=tool.description,
            annotations=tool.annotations,
            icons=tool.icons,
            meta=tool.meta,
        )


def build_http_mcp() -> FastMCP:
    host = (os.environ.get("MCP_HTTP_HOST") or "0.0.0.0").strip() or "0.0.0.0"
    port = int((os.environ.get("MCP_HTTP_PORT") or "10001").strip() or "10001")
    base = public_base_url()
    resource = mcp_resource_url()
    provider = KuchupOAuthProvider()
    auth = AuthSettings(
        issuer_url=AnyHttpUrl(base),
        resource_server_url=AnyHttpUrl(resource),
        required_scopes=["mcp"],
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=["mcp"],
            default_scopes=["mcp"],
        ),
        revocation_options=RevocationOptions(enabled=True),
    )
    http_mcp = FastMCP(
        "relocation-jobs",
        host=host,
        port=port,
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        auth=auth,
        auth_server_provider=provider,
    )
    _copy_tools(stdio_mcp, http_mcp)
    http_mcp.custom_route("/oauth/login", methods=["GET", "POST"])(_oauth_login)
    http_mcp.custom_route("/healthz", methods=["GET"])(oauth_health)
    return http_mcp


def run_http() -> None:
    build_http_mcp().run(transport="streamable-http")
