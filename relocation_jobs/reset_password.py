#!/usr/bin/env python3
"""Reset a panel user's password (e.g. after changing .env)."""

from __future__ import annotations

import argparse
import os
import sys

from relocation_jobs.core.auth import _hash_password
from relocation_jobs.core.paths import PROJECT_ROOT


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / ".env")
    except ImportError:
        pass


def main() -> int:
    _load_env()
    parser = argparse.ArgumentParser(description="Reset panel login password")
    parser.add_argument(
        "username",
        nargs="?",
        default=os.environ.get("PANEL_ADMIN_USER", "admin"),
    )
    parser.add_argument(
        "password",
        nargs="?",
        default=os.environ.get("PANEL_ADMIN_PASSWORD", ""),
    )
    parser.add_argument(
        "--rename-from",
        help="Rename this existing username to the target username first",
    )
    args = parser.parse_args()

    if not args.password:
        print("Password required (argument or PANEL_ADMIN_PASSWORD in .env)", file=sys.stderr)
        return 1

    from relocation_jobs.db import get_user_by_username, init_db, rename_user, update_user_password

    init_db()
    username = args.username.strip()
    if args.rename_from:
        old = get_user_by_username(args.rename_from)
        if not old:
            print(f"User not found: {args.rename_from}", file=sys.stderr)
            return 1
        if get_user_by_username(username) and old["username"].lower() != username.lower():
            print(f"Username already taken: {username}", file=sys.stderr)
            return 1
        rename_user(old["id"], username)
        print(f"Renamed {args.rename_from} → {username}")

    if not update_user_password(username, _hash_password(args.password)):
        print(f"User not found: {username}", file=sys.stderr)
        return 1

    print(f"Password updated for {username}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
