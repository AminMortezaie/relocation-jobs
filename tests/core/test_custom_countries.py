from __future__ import annotations

import pytest

from relocation_jobs.core.location_tags import (
    add_custom_city,
    add_custom_country,
    all_country_labels,
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
