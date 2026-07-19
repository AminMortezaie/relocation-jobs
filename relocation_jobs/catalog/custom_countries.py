from __future__ import annotations

import json

from relocation_jobs.core.db import db_read, db_transaction
from relocation_jobs.core.redis_client import get_redis, ping_redis, redis_enabled

COUNTRIES_REDIS_KEY = "countries:labels"
COUNTRIES_GENERATION_KEY = "countries:labels:generation"

DEFAULT_COUNTRY_LABELS: dict[str, str] = {
    "germany": "Germany",
    "netherlands": "Netherlands",
    "uk": "United Kingdom",
    "portugal": "Portugal",
}


def countries_use_redis() -> bool:
    return redis_enabled() and ping_redis()


def seed_default_countries(conn) -> None:
    for key, label in DEFAULT_COUNTRY_LABELS.items():
        conn.execute(
            """
            INSERT INTO custom_countries (country, label)
            VALUES (%s, %s)
            ON CONFLICT (country) DO NOTHING
            """,
            (key, label),
        )


def get_countries_generation() -> int:
    if not countries_use_redis():
        return 0
    raw = get_redis().get(COUNTRIES_GENERATION_KEY)
    if raw is None:
        return 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def bump_countries_generation() -> int:
    return int(get_redis().incr(COUNTRIES_GENERATION_KEY))


def load_countries_from_redis() -> dict[str, str]:
    raw = get_redis().hgetall(COUNTRIES_REDIS_KEY)
    return {
        str(key).strip().lower(): str(label).strip()
        for key, label in raw.items()
        if str(key).strip() and str(label).strip()
    }


def save_countries_to_redis(data: dict[str, str]) -> None:
    ordered = {
        key: data[key].strip()
        for key in sorted(data)
        if data[key].strip()
    }
    client = get_redis()
    pipe = client.pipeline()
    pipe.delete(COUNTRIES_REDIS_KEY)
    if ordered:
        pipe.hset(COUNTRIES_REDIS_KEY, mapping=ordered)
    pipe.incr(COUNTRIES_GENERATION_KEY)
    pipe.execute()


def upsert_country_in_redis(country_key: str, label: str) -> None:
    client = get_redis()
    pipe = client.pipeline()
    pipe.hset(COUNTRIES_REDIS_KEY, country_key, label.strip())
    pipe.incr(COUNTRIES_GENERATION_KEY)
    pipe.execute()


def remove_country_from_redis(country_key: str) -> bool:
    client = get_redis()
    pipe = client.pipeline()
    pipe.hdel(COUNTRIES_REDIS_KEY, country_key)
    pipe.incr(COUNTRIES_GENERATION_KEY)
    results = pipe.execute()
    return bool(results[0])


def load_custom_countries_from_db() -> dict[str, str]:
    with db_read() as conn:
        rows = conn.execute(
            "SELECT country, label FROM custom_countries ORDER BY country",
        ).fetchall()
    return {row["country"]: row["label"] for row in rows}


def load_country_labels_store() -> dict[str, str]:
    if countries_use_redis():
        return load_countries_from_redis()
    return load_custom_countries_from_db()


def _upsert_country_in_db(country_key: str, label: str) -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO custom_countries (country, label)
            VALUES (%s, %s)
            ON CONFLICT (country) DO UPDATE SET label = EXCLUDED.label
            """,
            (country_key, label.strip()),
        )


def _remove_country_from_db(country_key: str) -> bool:
    with db_transaction() as conn:
        cur = conn.execute(
            "DELETE FROM custom_countries WHERE country = %s RETURNING country",
            (country_key,),
        )
        return cur.fetchone() is not None


def save_custom_countries_to_db(data: dict[str, str]) -> None:
    ordered = {
        key: data[key].strip()
        for key in sorted(data)
        if data[key].strip()
    }
    with db_transaction() as conn:
        conn.execute("DELETE FROM custom_countries")
        for key, label in ordered.items():
            conn.execute(
                """
                INSERT INTO custom_countries (country, label)
                VALUES (%s, %s)
                """,
                (key, label),
            )


def save_country_labels_store(data: dict[str, str]) -> None:
    save_custom_countries_to_db(data)
    if countries_use_redis():
        save_countries_to_redis(data)


def upsert_custom_country(country_key: str, label: str) -> None:
    _upsert_country_in_db(country_key, label)
    if countries_use_redis():
        upsert_country_in_redis(country_key, label)


def remove_custom_country(country_key: str) -> bool:
    key = (country_key or "").strip().lower()
    if not key:
        return False
    removed_db = _remove_country_from_db(key)
    removed_redis = False
    if countries_use_redis():
        removed_redis = remove_country_from_redis(key)
    return removed_db or removed_redis


def list_catalog_country_keys() -> frozenset[str]:
    with db_read() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT country FROM companies
            UNION
            SELECT DISTINCT country FROM country_meta
            """,
        ).fetchall()
    return frozenset(
        (row["country"] or "").strip().lower()
        for row in rows
        if (row["country"] or "").strip()
    )


def migrate_custom_countries_from_json(conn) -> None:
    from relocation_jobs.core.location_tags import normalize_country_key
    from relocation_jobs.core.paths import data_dir

    path = data_dir() / "custom_countries.json"
    if not path.is_file():
        return
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(raw, dict):
        return
    for country, label in raw.items():
        country_key = normalize_country_key(str(country))
        if not country_key:
            continue
        if not isinstance(label, str) or not label.strip():
            continue
        conn.execute(
            """
            INSERT INTO custom_countries (country, label)
            VALUES (%s, %s)
            ON CONFLICT (country) DO UPDATE SET label = EXCLUDED.label
            """,
            (country_key, label.strip()),
        )


def init_countries_store() -> None:
    if not countries_use_redis():
        return
    client = get_redis()
    if client.hlen(COUNTRIES_REDIS_KEY) > 0:
        return
    merged = dict(DEFAULT_COUNTRY_LABELS)
    try:
        merged.update(load_custom_countries_from_db())
    except Exception:
        pass
    from relocation_jobs.core.location_tags import normalize_country_key
    from relocation_jobs.core.paths import data_dir

    path = data_dir() / "custom_countries.json"
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for country, label in raw.items():
                    country_key = normalize_country_key(str(country))
                    if country_key and isinstance(label, str) and label.strip():
                        merged[country_key] = label.strip()
        except (OSError, json.JSONDecodeError):
            pass
    save_countries_to_redis(merged)
