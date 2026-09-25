.PHONY: install dev run migrate makemigration downgrade current history test seed seed-yes clean

install:           ## install deps
	uv sync

dev:               ## run dev server (reload)
	uv run fastapi dev app.main:app

run:               ## run server (prod)
	uv run fastapi run app.main:app

migrate:           ## apply migrations
	uv run alembic upgrade head

makemigration:     ## autogenerate revision, e.g. make makemigration m="add x"
	uv run alembic revision --autogenerate -m "$(m)"

downgrade:         ## roll back one revision
	uv run alembic downgrade -1

current:           ## show current revision
	uv run alembic current

history:           ## show revision history
	uv run alembic history

test:              ## run test suite
	uv run pytest -q

seed:              ## seed dev database (destructive, asks first)
	uv run python scripts/seed.py --reset

seed-yes:          ## seed dev database without prompt
	uv run python scripts/seed.py --reset --yes

clean:             ## remove virtualenv
	rm -rf .venv
