.PHONY: setup up down migrate test lint shell

setup:
	cp -n .env.example .env || true
	pip install -r requirements.txt

up:
	docker compose up -d

down:
	docker compose down

migrate:
	alembic upgrade head

test:
	pytest tests/ -v --cov=. --cov-report=term-missing

lint:
	ruff check . --select E,F,W --ignore E501

shell:
	docker compose exec api bash

logs:
	docker compose logs -f api
