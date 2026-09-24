#!/bin/sh
# Container entrypoint: migrate, then exec the server.
# Exits non-zero if migrations fail so the container never serves stale schema.
set -e

echo "Applying database migrations..."
python -m alembic upgrade head

# Opt-in demo seeding. scripts/seed.py is DESTRUCTIVE (TRUNCATE ... CASCADE),
# so this only runs when explicitly enabled — never on plain restarts.
if [ "${SEED_ON_BOOT:-false}" = "true" ]; then
  echo "SEED_ON_BOOT=true: seeding database (destructive reset)..."
  python scripts/seed.py --reset --yes
fi

echo "Starting NaijaStay API..."
exec "$@"
