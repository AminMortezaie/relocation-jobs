# Test examples (relocation_jobs)

## Pure logic — `tests/test_location_tags_full.py`

```python
def test_custom_cities_persist(tmp_data_dir):
    from relocation_jobs.location_tags import (
        add_custom_city,
        custom_cities_path,
        load_custom_cities,
        picker_cities_for_country,
    )

    loc = add_custom_city("uk", "Reading")
    assert loc["city"] == "Reading"
    assert custom_cities_path().is_file()
    assert "Reading" in load_custom_cities()["uk"]
    assert "Reading" in picker_cities_for_country("uk")

    again = add_custom_city("uk", "reading")
    assert again["city"] == "Reading"
    assert load_custom_cities()["uk"].count("Reading") == 1
```

## API route — `tests/test_panel_api_full.py`

```python
@pytest.mark.integration
def test_locations_add_custom_city(auth_client, tmp_data_dir):
    resp = auth_client.post("/api/locations", json={"country": "uk", "city": "Reading"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["location"]["city"] == "Reading"

    picker = auth_client.get("/api/locations?country=uk&picker=true").get_json()
    keys = {loc["key"] for loc in picker["locations"]}
    assert "uk:reading" in keys

    assert auth_client.post("/api/locations", json={"country": "invalid", "city": "X"}).status_code == 400
    assert auth_client.post("/api/locations", json={"country": "uk", "city": ""}).status_code == 400
```

## Panel data — `tests/test_panel_data_full.py`

```python
@pytest.mark.integration
def test_list_locations_and_cities(rich_catalog):
    picker = list_company_locations("uk", for_picker=True)
    assert picker
    assert any(loc["city"] == "London" for loc in picker)
```

## Parametrized filters — `tests/test_panel_api_full.py`

```python
@pytest.mark.integration
@pytest.mark.parametrize("query", ["country=uk", "country=uk&visa_only=true"])
def test_jobs_list_filters(auth_client, rich_catalog, test_user, query):
    resp = auth_client.get(f"/api/jobs?{query}")
    assert resp.status_code == 200
    assert "companies" in resp.get_json()
```

## Scenario checklist template

When adding a feature, fill this in the PR or task notes:

```
Scenarios:
1. [happy path] -> test_...
2. [validation] -> test_...
3. [persistence] -> test_...
Run: .venv/bin/python -m pytest tests/... -q
```
