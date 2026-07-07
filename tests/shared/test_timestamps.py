from __future__ import annotations

import pytest

from relocation_jobs.shared.timestamps import normalize_posted_at


def test_normalize_posted_at_date_only():
    assert normalize_posted_at("2025-06-15") == "2025-06-15"


def test_normalize_posted_at_iso_datetime():
    assert normalize_posted_at("2025-06-15T14:30:00Z") == "2025-06-15T14:30:00+00:00"


def test_normalize_posted_at_rejects_invalid():
    with pytest.raises(ValueError, match="posted_at must be"):
        normalize_posted_at("not-a-date")
