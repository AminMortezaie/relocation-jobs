from __future__ import annotations

import pytest

from relocation_jobs.catalog import custom_countries as store
from relocation_jobs.core import location_tags


class _FakeRedis:
    def __init__(self) -> None:
        self._hashes: dict[str, dict[str, str]] = {}
        self._strings: dict[str, str] = {}

    def hlen(self, key: str) -> int:
        return len(self._hashes.get(key, {}))

    def hgetall(self, key: str) -> dict[str, str]:
        return dict(self._hashes.get(key, {}))

    def hset(self, key: str, field: str | None = None, value: str | None = None, mapping=None) -> None:
        bucket = self._hashes.setdefault(key, {})
        if mapping:
            bucket.update({str(k): str(v) for k, v in mapping.items()})
        elif field is not None and value is not None:
            bucket[str(field)] = str(value)

    def hdel(self, key: str, *fields: str) -> int:
        bucket = self._hashes.get(key, {})
        removed = 0
        for field in fields:
            if field in bucket:
                del bucket[field]
                removed += 1
        return removed

    def get(self, key: str):
        return self._strings.get(key)

    def incr(self, key: str) -> int:
        current = int(self._strings.get(key, "0"))
        current += 1
        self._strings[key] = str(current)
        return current

    def delete(self, key: str) -> None:
        self._hashes.pop(key, None)
        self._strings.pop(key, None)

    def pipeline(self):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, redis: _FakeRedis) -> None:
        self._redis = redis
        self._ops: list[tuple] = []

    def delete(self, key: str):
        self._ops.append(("delete", key))
        return self

    def hset(self, key: str, field: str | None = None, value: str | None = None, mapping=None):
        self._ops.append(("hset", key, field, value, mapping))
        return self

    def hdel(self, key: str, *fields: str):
        self._ops.append(("hdel", key, fields))
        return self

    def incr(self, key: str):
        self._ops.append(("incr", key))
        return self

    def execute(self) -> list:
        results = []
        for op in self._ops:
            if op[0] == "delete":
                self._redis.delete(op[1])
                results.append(1)
            elif op[0] == "hset":
                _, key, field, value, mapping = op
                self._redis.hset(key, field=field, value=value, mapping=mapping)
                results.append(1)
            elif op[0] == "hdel":
                results.append(self._redis.hdel(op[1], *op[2]))
            elif op[0] == "incr":
                results.append(self._redis.incr(op[1]))
        return results


@pytest.fixture
def fake_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(store, "get_redis", lambda: fake)
    monkeypatch.setattr(store, "ping_redis", lambda: True)
    monkeypatch.setattr(store, "countries_use_redis", lambda: True)
    return fake


def test_redis_country_upsert_and_load(fake_redis):
    store.save_countries_to_redis(store.DEFAULT_COUNTRY_LABELS)
    store.upsert_country_in_redis("armenia", "Armenia")
    labels = store.load_countries_from_redis()
    assert labels["armenia"] == "Armenia"
    assert labels["germany"] == "Germany"


def test_init_countries_store_seeds_redis_from_defaults(fake_redis):
    store.init_countries_store()
    labels = store.load_countries_from_redis()
    assert labels["uk"] == "United Kingdom"
    assert labels["portugal"] == "Portugal"


def test_upsert_custom_country_dual_writes_and_bumps_generation(fake_redis, monkeypatch):
    db_rows: dict[str, str] = {}

    def fake_upsert_db(country_key: str, label: str) -> None:
        db_rows[country_key] = label

    monkeypatch.setattr(store, "_upsert_country_in_db", fake_upsert_db)
    before = store.get_countries_generation()
    store.upsert_custom_country("armenia", "Armenia")
    assert db_rows["armenia"] == "Armenia"
    assert store.load_countries_from_redis()["armenia"] == "Armenia"
    assert store.get_countries_generation() == before + 1


def test_generation_aware_cache_sees_external_redis_write(fake_redis, monkeypatch):
    monkeypatch.setattr(
        "relocation_jobs.catalog.custom_countries.list_catalog_country_keys",
        lambda: frozenset(),
    )
    monkeypatch.setattr(location_tags, "_COUNTRIES_GENERATION_TTL_S", 0.0)

    store.save_countries_to_redis({"germany": "Germany"})
    location_tags._invalidate_custom_countries_cache()
    first = location_tags.all_country_labels()
    assert "armenia" not in first
    assert first["germany"] == "Germany"

    store.upsert_country_in_redis("armenia", "Armenia")
    second = location_tags.all_country_labels()
    assert second["armenia"] == "Armenia"


def test_hot_path_does_not_hammer_redis_within_ttl(fake_redis, monkeypatch):
    monkeypatch.setattr(
        "relocation_jobs.catalog.custom_countries.list_catalog_country_keys",
        lambda: frozenset(),
    )
    monkeypatch.setattr(location_tags, "_COUNTRIES_GENERATION_TTL_S", 5.0)

    get_calls = {"n": 0}
    real_get = fake_redis.get

    def counting_get(key):
        get_calls["n"] += 1
        return real_get(key)

    monkeypatch.setattr(fake_redis, "get", counting_get)

    store.save_countries_to_redis({"germany": "Germany"})
    location_tags._invalidate_custom_countries_cache()
    location_tags.all_country_labels()
    baseline = get_calls["n"]

    for _ in range(500):
        location_tags.country_label("germany")

    assert get_calls["n"] == baseline
