.PHONY: up down logs frontend migrate migrations test lint seed

up:
	docker compose up --build --remove-orphans

down:
	docker compose down --remove-orphans

logs:
	docker compose logs -f --tail=150

frontend:
	npm --prefix frontend run dev

migrate:
	docker compose exec backend python manage.py migrate

migrations:
	docker compose exec backend python manage.py makemigrations

test:
	docker compose exec backend pytest
	npm --prefix frontend run test -- --passWithNoTests

lint:
	docker compose exec backend ruff check .
	npm --prefix frontend run lint
	npm --prefix frontend run typecheck

seed:
	docker compose exec backend python manage.py seed_demo
