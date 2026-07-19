from __future__ import annotations

from html import escape

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse

from relocation_jobs.core.auth import authenticate
from relocation_jobs.mcp import oauth_repo
from relocation_jobs.mcp.oauth_provider import complete_login_redirect
from relocation_jobs.users.repo import get_user_by_id

_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title} — Kuchup MCP</title>
  <style>
    :root {{ color-scheme: light; --ink: #12141a; --muted: #5c6475; --line: #d8dde8; --bg: #f4f6fb; --card: #fff; --accent: #1f6b4a; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Segoe UI", system-ui, sans-serif; background: linear-gradient(160deg, #eef3ff, #f7faf7 55%, #fff); color: var(--ink); min-height: 100vh; display: grid; place-items: center; padding: 24px; }}
    .card {{ width: min(420px, 100%); background: var(--card); border: 1px solid var(--line); border-radius: 16px; padding: 28px; box-shadow: 0 18px 50px rgba(18, 20, 26, 0.08); }}
    h1 {{ margin: 0 0 8px; font-size: 1.35rem; }}
    p {{ margin: 0 0 18px; color: var(--muted); line-height: 1.45; font-size: 0.95rem; }}
    label {{ display: block; font-size: 0.85rem; font-weight: 600; margin: 0 0 6px; }}
    input {{ width: 100%; padding: 10px 12px; border: 1px solid var(--line); border-radius: 10px; margin-bottom: 14px; font: inherit; }}
    button {{ width: 100%; border: 0; border-radius: 10px; padding: 12px 14px; background: var(--accent); color: #fff; font: inherit; font-weight: 600; cursor: pointer; }}
    .error {{ background: #fdecec; color: #8a1f1f; border: 1px solid #f3c1c1; border-radius: 10px; padding: 10px 12px; margin-bottom: 14px; font-size: 0.9rem; }}
    .brand {{ font-size: 0.8rem; letter-spacing: 0.08em; text-transform: uppercase; color: var(--accent); font-weight: 700; margin-bottom: 10px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="brand">Kuchup</div>
    <h1>{heading}</h1>
    <p>{message}</p>
    {error}
    {body}
  </div>
</body>
</html>
"""


def _page(*, title: str, heading: str, message: str, body: str, error: str = "") -> HTMLResponse:
    err = f'<div class="error">{escape(error)}</div>' if error else ""
    html = _PAGE.format(
        title=escape(title),
        heading=escape(heading),
        message=message,
        error=err,
        body=body,
    )
    return HTMLResponse(html)


async def oauth_login_get(request: Request) -> HTMLResponse:
    request_id = (request.query_params.get("request_id") or "").strip()
    pending = oauth_repo.get_pending_request(request_id) if request_id else None
    if pending is None:
        return _page(
            title="Expired",
            heading="Authorization expired",
            message="Start again from Claude or Cursor — this login link is no longer valid.",
            body="",
        )
    body = f"""
    <form method="post" action="/oauth/login">
      <input type="hidden" name="request_id" value="{escape(request_id)}" />
      <label for="username">Username</label>
      <input id="username" name="username" autocomplete="username" required />
      <label for="password">Password</label>
      <input id="password" name="password" type="password" autocomplete="current-password" required />
      <p>Signing in allows Claude or Cursor to use your Kuchup application data (resumes, queue, tracking) for this account only.</p>
      <button type="submit">Allow access</button>
    </form>
    """
    return _page(
        title="Connect",
        heading="Connect MCP",
        message="Sign in with your Kuchup panel account to authorize this client.",
        body=body,
    )


async def oauth_login_post(request: Request) -> HTMLResponse | RedirectResponse:
    form = await request.form()
    request_id = str(form.get("request_id") or "").strip()
    username = str(form.get("username") or "").strip()
    password = str(form.get("password") or "")
    pending = oauth_repo.get_pending_request(request_id) if request_id else None
    if pending is None:
        return _page(
            title="Expired",
            heading="Authorization expired",
            message="Start again from Claude or Cursor — this login link is no longer valid.",
            body="",
        )
    user = authenticate(username, password)
    if user is None:
        body = f"""
        <form method="post" action="/oauth/login">
          <input type="hidden" name="request_id" value="{escape(request_id)}" />
          <label for="username">Username</label>
          <input id="username" name="username" value="{escape(username)}" autocomplete="username" required />
          <label for="password">Password</label>
          <input id="password" name="password" type="password" autocomplete="current-password" required />
          <p>Signing in allows Claude or Cursor to use your Kuchup application data for this account only.</p>
          <button type="submit">Allow access</button>
        </form>
        """
        return _page(
            title="Connect",
            heading="Connect MCP",
            message="Sign in with your Kuchup panel account to authorize this client.",
            body=body,
            error="Invalid username or password",
        )
    redirect_url = complete_login_redirect(request_id=request_id, user_id=int(user["id"]))
    return RedirectResponse(url=redirect_url, status_code=302, headers={"Cache-Control": "no-store"})


async def oauth_health(_request: Request) -> HTMLResponse:
    return HTMLResponse("ok")


def username_for_subject(subject: str | None) -> str:
    if not subject:
        return ""
    user = get_user_by_id(int(subject)) or {}
    return (user.get("username") or "").strip()
