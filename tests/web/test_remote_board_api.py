from __future__ import annotations

from relocation_jobs.catalog.repo import get_company, sync_aggregator_employer_jobs, upsert_company
from relocation_jobs.scrape.aggregator_seeds import ensure_aggregator_seeds
from relocation_jobs.scrape.aggregator_sync import sync_aggregator_board
from relocation_jobs.scrape.merge import now_iso


def _seed_relocation_company():
    ts = now_iso()
    upsert_company(
        "uk",
        {
            "name": "Acme Relo",
            "city": "London",
            "size": "51-200",
            "careers_url": "https://boards.greenhouse.io/acmerelo",
            "ats_type": "greenhouse",
            "ats_url": "https://boards.greenhouse.io/acmerelo",
            "matching_jobs": [
                {
                    "title": "Backend Engineer",
                    "url": "https://boards.greenhouse.io/acmerelo/jobs/1",
                    "fetched": ts,
                    "last_seen": ts,
                }
            ],
            "sources": ["panel"],
            "added": ts,
            "updated": ts,
        },
        updated=ts,
    )


def test_relocation_board_excludes_remote_catalog(v2_auth_client, db):
    ensure_aggregator_seeds()
    _seed_relocation_company()
    source = get_company("remote-ok", "Remote OK")
    assert source is not None
    sync_aggregator_board(
        "remote-ok",
        source,
        [
            {
                "title": "Platform Engineer",
                "url": "https://remoteOK.com/remote-jobs/orbit-1",
                "employer": "Orbit Remote",
            }
        ],
    )

    relo = v2_auth_client.get("/api/board?country=all").get_json()
    names = {c["name"] for c in relo["companies"]}
    assert "Acme Relo" in names
    assert "Orbit Remote" not in names
    assert "Remote OK" not in names

    uae = v2_auth_client.get("/api/board?country=uae").get_json()
    assert all(c.get("ats_type") != "sourced" for c in uae["companies"])
    assert all(c.get("ats_type") != "remotedxb" for c in uae["companies"])


def test_remote_board_includes_only_remote_catalog(v2_auth_client, db):
    ensure_aggregator_seeds()
    _seed_relocation_company()
    sync_aggregator_employer_jobs(
        "remote-dxb",
        "DXB Corp",
        [
            {
                "title": "Remote Engineer",
                "url": "https://www.remotedxb.com/jobs/1",
                "fetched": now_iso(),
                "last_seen": now_iso(),
            }
        ],
        source="remotedxb",
        careers_url="https://www.remotedxb.com/rss",
    )

    remote = v2_auth_client.get("/api/remote/board?country=all").get_json()
    names = {c["name"] for c in remote["companies"]}
    assert "DXB Corp" in names
    assert "Acme Relo" not in names
    assert remote["meta"]["catalog_kind"] == "remote"

    countries = v2_auth_client.get("/api/remote/countries").get_json()
    ids = {c["id"] for c in countries}
    assert "remote-ok" in ids
    assert "remote-dxb" in ids
    assert "remote-joblet" in ids
    assert "uk" not in ids

    relo_countries = v2_auth_client.get("/api/countries").get_json()
    relo_ids = {c["id"] for c in relo_countries}
    assert "remote-ok" not in relo_ids
    assert "remote-dxb" not in relo_ids
    assert "remote-joblet" not in relo_ids


def test_remote_panel_route_serves_shell(v2_auth_client):
    resp = v2_auth_client.get("/remote")
    assert resp.status_code == 200
    assert b"panelNavRemote" in resp.data
