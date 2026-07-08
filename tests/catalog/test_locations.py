from __future__ import annotations

from relocation_jobs.catalog.locations import list_company_locations


def test_list_company_locations_picker_uses_company_rows(seeded_catalog_v2):
    del seeded_catalog_v2
    locations = list_company_locations(for_picker=True)
    assert isinstance(locations, list)
    keys = {loc["key"] for loc in locations}
    assert all(":" in key for key in keys)


def test_list_company_locations_country_filter(seeded_catalog_v2):
    del seeded_catalog_v2
    locations = list_company_locations("uk", for_picker=False)
    assert all(loc["country"] == "uk" for loc in locations)
