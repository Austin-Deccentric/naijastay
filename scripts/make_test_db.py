"""Provision the dedicated test database (idempotent) and migrate it.

Reads TEST_DATABASE_URL from `.env` (or the environment), CREATEs the
database if missing via the `postgres` admin db, then runs
`alembic upgrade head` against the test URL. Safe to re-run.

Usage: `make test-db` (or `uv run python scripts/make_test_db.py`).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from urllib.parse import urlparse


def load_dotenv(path: str = ".env") -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip().strip("\"'")
    except FileNotFoundError:
        pass
    return values


def main() -> None:
    file_env = load_dotenv()
    test_url = os.environ.get("TEST_DATABASE_URL", "").strip() or file_env.get(
        "TEST_DATABASE_URL", ""
    ).strip()
    if not test_url:
        raise SystemExit("TEST_DATABASE_URL is not set (.env or environment).")

    dbname = urlparse(test_url).path.lstrip("/")
    if "test" not in dbname:
        raise SystemExit(
            f"Refusing to provision non-test database '{dbname}'."
        )
    if not re.fullmatch(r"[A-Za-z0-9_]+", dbname):
        raise SystemExit(f"Unsafe database name '{dbname}'.")

    import psycopg

    # Sync psycopg takes a libpq URL, not the SQLAlchemy driver form.
    admin_url = re.sub(r"/[^/]+$", "/postgres", test_url).replace(
        "postgresql+psycopg://", "postgresql://"
    ).replace("postgres+psycopg://", "postgres://")
    with psycopg.connect(admin_url, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)
        ).fetchone()
        if exists:
            print(f"Database {dbname} exists, skipping create.")
        else:
            conn.execute(f'CREATE DATABASE "{dbname}"')
            print(f"Created database {dbname}.")

    env = {**os.environ, "DATABASE_URL": test_url}
    print(f"Applying migrations to {dbname}...")
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=env,
        check=True,
    )
    print("Test database ready.")


if __name__ == "__main__":
    main()
