from __future__ import annotations

import pytest

from relocation_jobs.core.location_tags import (
    add_custom_city,
    add_custom_country,
    all_country_labels,
    ensure_country_key,
    load_custom_countries,
    normalize_location,
    supported_country_keys,
)


def test_add_custom_country_persists(tmp_data_dir):
    saved = add_custom_country("Spain")
    assert saved == {"id": "spain", "label": "Spain"}
    assert load_custom_countries() == {"spain": "Spain"}
    assert "spain" in supported_country_keys()
    assert all_country_labels()["spain"] == "Spain"


def test_add_custom_country_returns_builtin_match(tmp_data_dir):
    saved = add_custom_country("Germany")
    assert saved == {"id": "germany", "label": "Germany"}
    assert load_custom_countries() == {}


def test_add_custom_country_rejects_empty(tmp_data_dir):
    with pytest.raises(ValueError, match="required"):
        add_custom_country("")


def test_ensure_country_key_registers_unknown(tmp_data_dir):
    assert ensure_country_key("armenia") == "armenia"
    assert load_custom_countries() == {"armenia": "Armenia"}
    assert ensure_country_key("armenia") == "armenia"


def test_custom_country_allows_custom_city(tmp_data_dir):
    add_custom_country("Spain")
    loc = add_custom_city("spain", "Barcelona")
    assert loc == {
        "country": "spain",
        "city": "Barcelona",
        "country_label": "Spain",
        "key": "spain:barcelona",
        "label": "Barcelona (Spain)",
    }
    assert normalize_location("spain", "Barcelona") == loc


def test_country_archive_filename_for_custom_country():
    from relocation_jobs.core.paths import country_archive_filename

    assert country_archive_filename("uk") == "uk_companies.json"
    assert country_archive_filename("ireland") == "ireland_companies.json"


def test_normalize_location_strips_custom_country_suffix(tmp_data_dir):
    add_custom_country("Ireland")
    loc = normalize_location("ireland", "Dublin (Ireland)")
    assert loc is not None
    assert loc["city"] == "Dublin"
    assert loc["label"] == "Dublin (Ireland)"


def test_sync_company_location_fields_no_double_suffix(tmp_data_dir):
    from relocation_jobs.core.location_tags import sync_company_location_fields

    add_custom_country("Ireland")
    company = {"locations": [{"country": "ireland", "city": "Dublin (Ireland)"}]}
    sync_company_location_fields(company, catalog_country="ireland")
    assert company["city"] == "Dublin (Ireland)"
    assert len(company["locations"]) == 1
    assert company["locations"][0]["city"] == "Dublin"
