#!/bin/sh
# Container entrypoint: migrate, then exec the server.
# Exits non-zero if migrations fail so the container never serves stale schema.
set -e

echo "Applying database migrations..."
python -m alembic upgrade head

# Opt-in demo seeding. scripts/seed.py is DESTRUCTIVE (TRUNCATE ... CASCADE),
# so this only runs when explicitly enabled — never on plain restarts.
# The seeder is currently not shipped in the image; skip gracefully when absent.
if [ "${SEED_ON_BOOT:-false}" = "true" ]; then
  if [ -f scripts/seed.py ]; then
    echo "SEED_ON_BOOT=true: seeding database (destructive reset)..."
    python scripts/seed.py --reset --yes
  else
    echo "SEED_ON_BOOT=true but scripts/seed.py is absent from the image; skipping seed."
  fi
fi

echo "Starting NaijaStay API..."
exec "$@"
