"""Test password hashing compatible with Python builds lacking hashlib.scrypt."""

from __future__ import annotations

from werkzeug.security import generate_password_hash

TEST_PASSWORD_METHOD = "pbkdf2:sha256"


def hash_test_password(password: str) -> str:
    return generate_password_hash(password, method=TEST_PASSWORD_METHOD)
