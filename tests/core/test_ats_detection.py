from __future__ import annotations

from relocation_jobs.core import ats_detection as mod


def test_recruitee_careers_host_requires_live_board(monkeypatch):
    monkeypatch.setattr(mod, "_recruitee_board_exists", lambda slug: slug == "realco")
    monkeypatch.setattr(mod, "_recruitee_board_has_real_jobs", lambda slug: slug == "realco")
    assert mod._detect_recruitee_from_careers_host("https://careers.criteo.com/") == (None, None)
    assert mod._detect_recruitee_from_careers_host("https://careers.realco.com/") == (
        "recruitee",
        "https://realco.recruitee.com/",
    )


def test_accept_url_ats_detection_rejects_missing_recruitee_board(monkeypatch):
    monkeypatch.setattr(mod, "_recruitee_board_exists", lambda slug: False)
    assert mod._accept_url_ats_detection("recruitee", "https://criteo.recruitee.com/") == (None, None)


def test_detect_teamtailor_embedded_on_custom_careers_host():
    html = '<script src="https://assets-aws.teamtailor-cdn.com/assets/packs/js/runtime.js"></script>'
    ats_type, ats_url = mod._detect_teamtailor_embedded(html, "https://careers.teamviewer.com/jobs")
    assert ats_type == "teamtailor"
    assert ats_url == "https://careers.teamviewer.com/jobs"


def test_detect_ats_static_finds_workday_for_criteo(monkeypatch):
    monkeypatch.setattr(mod, "_recruitee_board_exists", lambda slug: False)

    class _Resp:
        text = (
            '<a href="https://criteo.wd3.myworkdayjobs.com/en-US/CriteoCareers">Jobs</a>'
        )
        url = "https://careers.criteo.com/"

    monkeypatch.setattr(mod.requests, "get", lambda *args, **kwargs: _Resp())
    ats_type, ats_url = mod.detect_ats_static("https://careers.criteo.com/")
    assert ats_type == "workday"
    assert ats_url and "criteo.wd3.myworkdayjobs.com" in ats_url


def test_detect_ats_static_finds_teamtailor_for_teamviewer(monkeypatch):
    monkeypatch.setattr(mod, "_recruitee_board_exists", lambda slug: False)
    ats_type, ats_url = mod.detect_ats_static("https://careers.teamviewer.com/")
    assert ats_type == "teamtailor"
    assert ats_url == "https://careers.teamviewer.com"
