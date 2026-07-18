.PHONY: dev-product-backend dev-labs-backend dev-product-frontend dev-labs-frontend build-product build-labs delivery test-product postgres-config postgres-setup postgres-migrate sqlbot-up sqlbot-down sqlbot-config verify-postgres-sqlbot

dev-product-backend:
	uvicorn backend.main:app --reload --port 8000

dev-labs-backend:
	uvicorn backend.labs_main:app --reload --port 8001

dev-product-frontend:
	npm --prefix frontend run dev:product

dev-labs-frontend:
	npm --prefix frontend run dev:labs

build-product:
	npm --prefix frontend run build:product

build-labs:
	npm --prefix frontend run build:labs

delivery:
	python3 scripts/build_delivery.py

postgres-config:
	.venv/bin/python scripts/configure_local_postgres_env.py

postgres-setup:
	.venv/bin/python scripts/setup_local_postgres.py

postgres-migrate:
	.venv/bin/python scripts/migrate_receivables_sqlite.py

sqlbot-up:
	docker compose -f infra/sqlbot/compose.yml up -d

sqlbot-down:
	docker compose -f infra/sqlbot/compose.yml down

sqlbot-config:
	.venv/bin/python scripts/configure_sqlbot.py

verify-postgres-sqlbot:
	.venv/bin/python scripts/verify_postgres_sqlbot.py

test-product:
	.venv/bin/python -m unittest tests.test_auth_session tests.test_collection_sync_service tests.test_notification_tasks tests.test_overdue_service tests.test_postgres_receivable_store tests.test_receivable_match tests.test_receivable_notify tests.test_sqlbot_embed tests.test_yonyou_finance tests.test_yonyou_sales
