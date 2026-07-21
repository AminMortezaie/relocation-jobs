from __future__ import annotations

from relocation_jobs.catalog.repo import get_company, list_country_company_stubs
from relocation_jobs.scrape.aggregator_seeds import ensure_aggregator_seeds
from relocation_jobs.scrape.aggregator_sync import sync_aggregator_board


def test_ensure_aggregator_seeds_creates_countries_and_sources(db):
    created = ensure_aggregator_seeds()
    assert {row["company"] for row in created} >= {"Remote OK", "Remote DXB"}
    again = ensure_aggregator_seeds()
    assert again == []
    remote_ok = get_company("remote-ok", "Remote OK")
    assert remote_ok is not None
    assert remote_ok["ats_type"] == "remoteok"
    dxb = get_company("uae", "Remote DXB")
    assert dxb is not None
    assert dxb["ats_type"] == "remotedxb"


def test_sync_aggregator_board_fans_out_employers(db):
    ensure_aggregator_seeds()
    source = get_company("remote-ok", "Remote OK")
    assert source is not None
    employers, job_total = sync_aggregator_board(
        "remote-ok",
        source,
        [
            {
                "title": "Senior Backend Engineer",
                "url": "https://remoteOK.com/remote-jobs/acme-backend-1",
                "employer": "Acme Labs",
                "description_text": "APIs",
            },
            {
                "title": "Platform Engineer",
                "url": "https://remoteOK.com/remote-jobs/orbit-platform-2",
                "employer": "Orbit",
            },
            {
                "title": "Sales Director",
                "url": "https://remoteOK.com/remote-jobs/sales-3",
                "employer": "SalesCo",
            },
        ],
    )
    assert employers == 2
    assert job_total == 2
    acme = get_company("remote-ok", "Acme Labs")
    assert acme is not None
    assert acme["ats_type"] == "sourced"
    assert len(acme["matching_jobs"]) == 1
    assert acme["matching_jobs"][0]["title"] == "Senior Backend Engineer"
    stubs = list_country_company_stubs("remote-ok")
    sourced = [s for s in stubs if s["ats_type"] == "sourced"]
    assert {s["name"] for s in sourced} >= {"Acme Labs", "Orbit"}
