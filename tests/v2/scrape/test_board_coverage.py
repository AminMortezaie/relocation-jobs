from __future__ import annotations

from relocation_jobs.core.ats_constants import ATS_TYPE_CHOICES
from relocation_jobs.v2.scrape.board import assert_full_ats_coverage, supported_ats_types


def test_all_ats_type_choices_have_board_fetcher():
    assert_full_ats_coverage()
    assert supported_ats_types() == {key for key, _ in ATS_TYPE_CHOICES}
