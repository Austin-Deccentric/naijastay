.PHONY: install dev run migrate makemigration downgrade current history clean

install:           ## install deps
	uv sync

dev:               ## run dev server (reload)
	uv run fastapi dev src.app.main:app

run:               ## run server (prod)
	uv run fastapi run src.app.main:app

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

clean:             ## remove virtualenv
	rm -rf .venv
