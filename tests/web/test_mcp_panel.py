from __future__ import annotations


def test_mcp_profile_round_trip(v2_auth_client):
    empty = v2_auth_client.get("/api/mcp/profile")
    assert empty.status_code == 200
    assert empty.get_json()["profile"]["full_name"] == ""
    assert empty.get_json()["profile"]["pipeline"] == []

    saved = v2_auth_client.put(
        "/api/mcp/profile",
        json={
            "full_name": "Jane Applicant",
            "email": "jane@example.com",
            "phone": "+1 555 0100",
            "linkedin_url": "https://linkedin.com/in/jane",
            "location": "Amsterdam",
            "work_authorization": "EU citizen",
            "notice_period": "4 weeks",
            "summary": "Backend engineer",
            "pipeline": [
                "Emphasize distributed systems experience.",
                "Keep the resume under two pages.",
            ],
        },
    )
    assert saved.status_code == 200
    payload = saved.get_json()
    assert payload["ok"] is True
    assert payload["profile"]["full_name"] == "Jane Applicant"
    assert payload["profile"]["pipeline"] == [
        "Emphasize distributed systems experience.",
        "Keep the resume under two pages.",
    ]

    loaded = v2_auth_client.get("/api/mcp/profile")
    assert loaded.status_code == 200
    assert loaded.get_json()["profile"]["email"] == "jane@example.com"
    assert len(loaded.get_json()["profile"]["pipeline"]) == 2


def test_mcp_profile_pipeline_max_five(v2_auth_client):
    resp = v2_auth_client.put(
        "/api/mcp/profile",
        json={
            "full_name": "Jane",
            "pipeline": [f"prompt {i}" for i in range(6)],
        },
    )
    assert resp.status_code == 400


def test_mcp_master_resume_round_trip(v2_auth_client):
    tex = r"""
\documentclass{article}
\begin{document}
Hello world
\end{document}
"""
    saved = v2_auth_client.put(
        "/api/mcp/master-resumes/fullstack",
        json={"content": tex, "label": "Full stack"},
    )
    assert saved.status_code == 200
    body = saved.get_json()
    assert body["ok"] is True
    assert body["slug"] == "fullstack"
    assert body["label"] == "Full stack"

    listing = v2_auth_client.get("/api/mcp/master-resumes")
    assert listing.status_code == 200
    items = listing.get_json()["items"]
    assert len(items) == 1
    assert items[0]["slug"] == "fullstack"
    assert items[0]["label"] == "Full stack"

    detail = v2_auth_client.get("/api/mcp/master-resumes/fullstack")
    assert detail.status_code == 200
    assert "Hello world" in detail.get_json()["content"]


def test_mcp_routes_require_auth(v2_client):
    assert v2_client.get("/api/mcp/profile").status_code == 401
    assert v2_client.get("/api/mcp/master-resumes").status_code == 401


def test_mcp_profile_isolated_per_user(v2_auth_client, auth_client):
    v2_auth_client.put(
        "/api/mcp/profile",
        json={"full_name": "Admin User", "email": "admin@example.com"},
    )

    register = auth_client.post(
        "/api/auth/register",
        json={"username": "otheruser", "password": "otherpass123"},
    )
    assert register.status_code == 200

    other = auth_client.get("/api/mcp/profile")
    assert other.status_code == 200
    assert other.get_json()["profile"]["full_name"] == ""


def test_apply_page_served(v2_client):
    resp = v2_client.get("/apply")
    assert resp.status_code == 200
    assert b"Application data" in resp.data
