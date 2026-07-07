from __future__ import annotations

import pytest

from relocation_jobs.catalog import custom_countries as store


class _FakeRedis:
    def __init__(self) -> None:
        self._hashes: dict[str, dict[str, str]] = {}

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

    def delete(self, key: str) -> None:
        self._hashes.pop(key, None)

    def pipeline(self):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, redis: _FakeRedis) -> None:
        self._redis = redis
        self._ops: list[tuple] = []

    def delete(self, key: str):
        self._ops.append(("delete", key))
        return self

    def hset(self, key: str, mapping: dict[str, str]):
        self._ops.append(("hset", key, mapping))
        return self

    def execute(self) -> None:
        for op in self._ops:
            if op[0] == "delete":
                self._redis.delete(op[1])
            elif op[0] == "hset":
                self._redis.hset(op[1], mapping=op[2])


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
