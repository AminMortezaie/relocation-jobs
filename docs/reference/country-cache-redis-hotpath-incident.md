# How a "cache invalidation" fix took the board down again

**Last updated:** 2026-07-18
**Status:** resolved (local panel + EC2 Postgres/Redis dev setup)

This is a story about a one-line-looking feature — "make country labels refresh across processes" — that quietly reintroduced the exact performance collapse a previous postmortem had already fixed. The board went from ~1.7s back to unusable. The lesson is old but keeps biting: **never put network I/O inside a helper that runs in a hot loop, even if that helper looks like a cheap cache read.**

Read this alongside [board-load-performance-incident.md](board-load-performance-incident.md) — this incident is its sequel.

---

## Executive summary

| | |
|---|---|
| **Symptom** | Board load collapsed again (tens of seconds) right after shipping cross-process country-label invalidation. |
| **Trigger** | A new feature: MCP-added countries should appear in the panel without a restart. |
| **Root cause** | The generation-aware cache checked Redis on **every** call to `all_country_labels()` / `country_label()`. Those run in a per-company loop, so each board load fired hundreds of Redis round-trips. |
| **Why it hid** | Locally with `REDIS_URL` unset the check short-circuits, so tests and no-Redis dev never saw it. With Redis on (the real deploy) it detonated. |
| **Fix** | Throttle the cross-process generation check to at most once every 5s; the hot path stays 100% in-memory. |
| **Outcome** | Board back to ~1.3–1.7s; cross-process propagation lags ≤5s (acceptable). |

---

## Background: the store and the cache

Country labels (e.g. `germany` → `Germany`) live in Postgres `custom_countries`, with Redis (`countries:labels` hash) as a hot read replica. They are read *constantly*: filters, display, and — critically — location normalization for every company on the board.

The previous incident ([board-load-performance-incident.md](board-load-performance-incident.md)) fixed a version where `all_country_labels()` hit Postgres on every call inside a loop. The fix was a plain in-memory cache:

```python
_country_labels_cache: dict[str, str] | None = None

def all_country_labels() -> dict[str, str]:
    global _country_labels_cache
    if _country_labels_cache is not None:
        return _country_labels_cache
    merged = dict(load_custom_countries())
    for key in list_catalog_country_keys():
        merged.setdefault(key, key.replace("-", " ").title())
    _country_labels_cache = merged
    return merged
```

That cache is process-local. It is only cleared when *this* process performs a country write. That was fine — until we added a feature that broke the assumption.

---

## The feature that caused it

The panel (Flask) and the MCP server run as **separate processes**. When Claude added a country via MCP, the MCP process invalidated *its own* cache, but the long-running panel kept serving the stale list until someone restarted it. The requested behavior: the panel should pick up MCP-added countries automatically.

The chosen design was sound: keep Postgres as the source of truth, mirror writes into Redis, and bump a Redis generation counter (`countries:labels:generation`) on every write. Any process can compare "the generation I cached against" with "the current generation in Redis" and reload only when they differ.

The write side was fine:

```python
# relocation_jobs/catalog/custom_countries.py
def upsert_custom_country(country_key: str, label: str) -> None:
    _upsert_country_in_db(country_key, label)      # Postgres: source of truth
    if countries_use_redis():
        upsert_country_in_redis(country_key, label)  # mirror + INCR generation
```

The read side is where it went wrong.

---

## The bug

I made the cache "generation-aware" by consulting Redis on every read:

```python
# THE BUG — runs on every all_country_labels() / country_label() call
def _countries_generation_is_current() -> bool:
    from relocation_jobs.catalog.custom_countries import (
        countries_use_redis,
        get_countries_generation,
    )
    if not countries_use_redis():        # Redis PING  (round-trip #1)
        return True
    current = get_countries_generation() # Redis GET   (round-trip #2)
    if _countries_cache_generation is None:
        return False
    return _countries_cache_generation == current


def all_country_labels() -> dict[str, str]:
    global _country_labels_cache
    if _country_labels_cache is not None and _countries_generation_is_current():
        return _country_labels_cache      # "cache hit" that still hit Redis twice
    ...
```

It reads like a cache hit. It is not. Every "hit" performs two Redis round-trips:

1. `countries_use_redis()` → `redis_enabled() and ping_redis()` — a Redis **PING**.
2. `get_countries_generation()` — a Redis **GET**.

Now recall where `country_label()` is called:

```python
def country_label(country: str) -> str:
    key = normalize_country_key(country)
    return all_country_labels().get(key, key.title() if key else "")
```

`country_label()` runs inside `sync_company_location_fields()` — once per company (and per city) on every board render. For a country with ~100 companies that is hundreds of calls, and now **each call makes two network round-trips to Redis**. The in-memory cache the earlier postmortem introduced was effectively disabled. Same failure shape as the original 678-DB-round-trip incident, just with Redis instead of Postgres.

### Why it slipped through review and tests

The killer detail: with `REDIS_URL` unset, `countries_use_redis()` returns `False` and the function returns immediately. So:

- Local dev without Redis: fine.
- The unit tests (which stub Redis narrowly): fine.
- The actual deployment with Redis enabled: catastrophic.

The bug was invisible in exactly the environments where we looked at it, and only lived in the one where we didn't.

---

## The fix

The insight: cross-process propagation does **not** need to be instantaneous. A new country appearing a few seconds later is completely acceptable for a panel. So we throttle the Redis generation check with a short TTL and keep the hot path in pure memory:

```python
# relocation_jobs/core/location_tags.py
_countries_generation_checked_at: float = 0.0
_COUNTRIES_GENERATION_TTL_S = 5.0

def _countries_generation_is_current() -> bool:
    global _countries_generation_checked_at
    now = time.monotonic()
    if now - _countries_generation_checked_at < _COUNTRIES_GENERATION_TTL_S:
        return True                      # hot path: zero I/O

    from relocation_jobs.catalog.custom_countries import (
        countries_use_redis,
        get_countries_generation,
    )
    _countries_generation_checked_at = now
    if not countries_use_redis():
        return True
    if _countries_cache_generation is None:
        return False
    return _countries_cache_generation == get_countries_generation()
```

Now a board load that calls `country_label()` hundreds of times performs **at most one** Redis check every 5 seconds; every other call short-circuits on an in-memory timestamp comparison. Local writes still clear the cache and reset the throttle, so changes made in *this* process are instant; other processes converge within ≤5s — which is the whole point of the feature, minus the self-inflicted DDoS.

### Guarding it with a test

The real regression was "hot path hammers Redis," so the test asserts exactly that — repeated calls within the TTL cause zero additional Redis reads:

```python
def test_hot_path_does_not_hammer_redis_within_ttl(fake_redis, monkeypatch):
    monkeypatch.setattr(location_tags, "_COUNTRIES_GENERATION_TTL_S", 5.0)

    get_calls = {"n": 0}
    real_get = fake_redis.get
    def counting_get(key):
        get_calls["n"] += 1
        return real_get(key)
    monkeypatch.setattr(fake_redis, "get", counting_get)

    location_tags._invalidate_custom_countries_cache()
    location_tags.all_country_labels()
    baseline = get_calls["n"]

    for _ in range(500):
        location_tags.country_label("germany")

    assert get_calls["n"] == baseline   # 500 hot-path calls, 0 extra Redis GETs
```

The cross-process propagation test forces `_COUNTRIES_GENERATION_TTL_S = 0.0` to assert the generation logic itself, independent of the throttle.

---

## Timings

| Endpoint (warm, EC2 Postgres + Redis) | Broken | After fix |
|---------------------------------------|--------|-----------|
| `country_label()` in board loop | 2 Redis round-trips × N companies | in-memory, 0 I/O |
| `/api/public/overview` | seconds, climbing | ~1.35s (stable) |
| `/api/public/preview?limit=50` | seconds, climbing | ~1.6s (stable) |

---

## Lessons

**A cache read that does I/O is not a cache.** The moment `all_country_labels()` touched Redis on the "hit" path, it stopped being a cache and became a synchronous network call wearing a cache's clothes.

**Know your hot paths before you add I/O.** `country_label()` looks trivial. It runs per-company per-board-load. The previous postmortem said this in bold; this incident is proof the warning has to be internalized, not just read.

**Beware short-circuits that hide cost in the wrong environment.** `if not countries_use_redis(): return True` made the expensive branch invisible in no-Redis dev and tests, and only active in production. If a code path behaves differently with Redis on, test it with Redis on.

**Eventual consistency is a feature, not a failure.** Requiring instant cross-process propagation forced a per-call check. Accepting ≤5s staleness removed the entire problem. Pick the weakest consistency the product actually needs.

**Add the test that encodes the failure, not just the behavior.** "Does the new country show up" passes even with the bug. "Does the hot path stay off Redis" is the test that would have caught it.

---

## Files

- [`relocation_jobs/core/location_tags.py`](../../relocation_jobs/core/location_tags.py) — throttled generation check, in-memory hot path
- [`relocation_jobs/catalog/custom_countries.py`](../../relocation_jobs/catalog/custom_countries.py) — dual-write + `countries:labels:generation`
- [`tests/catalog/test_countries_redis.py`](../../tests/catalog/test_countries_redis.py) — hot-path and propagation tests

Related: [board-load-performance-incident.md](board-load-performance-incident.md), [catalog-pattern.md](catalog-pattern.md), [operations/ec2-panel.md](../operations/ec2-panel.md)
