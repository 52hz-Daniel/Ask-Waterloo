.PHONY: bootstrap dev down seed-demo test test-integration verify

bootstrap:
	docker compose build
	docker compose run --rm migrate
	docker compose run --rm seed

dev:
	docker compose up --build web api worker db

down:
	docker compose down --remove-orphans

seed-demo:
	docker compose run --rm migrate
	docker compose run --rm seed

test:
	docker compose run --rm api pytest -q tests/test_rules.py tests/test_contracts.py

test-integration:
	docker compose run --rm migrate
	docker compose run --rm seed
	docker compose run --rm api pytest -q tests/test_integration.py tests/test_telemetry.py

verify:
	docker compose --profile checks build
	docker compose run --rm migrate
	docker compose run --rm seed
	docker compose run --rm api ruff check app tests
	docker compose run --rm api mypy app
	docker compose run --rm api pytest -q
	docker compose run --rm web-check npm run lint
	docker compose run --rm web-check npm run typecheck
	docker compose run --rm web-check npm run build
