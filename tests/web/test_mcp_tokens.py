from __future__ import annotations


def test_mcp_connect_info_requires_auth(v2_client):
    assert v2_client.get("/api/mcp/connect-info").status_code == 401


def test_mcp_tokens_require_auth(v2_client):
    assert v2_client.get("/api/mcp/tokens").status_code == 401
    assert v2_client.post("/api/mcp/tokens", json={"label": "x"}).status_code == 401
    assert v2_client.delete("/api/mcp/tokens/1").status_code == 401


def test_mcp_connect_info_and_token_lifecycle(v2_auth_client):
    info = v2_auth_client.get("/api/mcp/connect-info")
    assert info.status_code == 200
    body = info.get_json()
    assert body["mcp_url"].endswith("/mcp")
    assert "kuchup.com" in body["mcp_url"] or "127.0.0.1" in body["mcp_url"] or "localhost" in body["mcp_url"]

    created = v2_auth_client.post("/api/mcp/tokens", json={"label": "ci"})
    assert created.status_code == 200
    payload = created.get_json()
    assert payload["ok"] is True
    assert payload["token"].startswith("kch_")
    token_id = payload["id"]

    listed = v2_auth_client.get("/api/mcp/tokens")
    assert listed.status_code == 200
    items = listed.get_json()["items"]
    assert any(item["id"] == token_id and item["label"] == "ci" and not item["revoked"] for item in items)

    revoked = v2_auth_client.delete(f"/api/mcp/tokens/{token_id}")
    assert revoked.status_code == 200
    listed2 = v2_auth_client.get("/api/mcp/tokens")
    match = next(item for item in listed2.get_json()["items"] if item["id"] == token_id)
    assert match["revoked"] is True
