# ─────────────────────────────────────────────────────────────────────────────
# AlcoaBase — Developer Makefile
# ─────────────────────────────────────────────────────────────────────────────
.PHONY: help up down rebuild logs backend-logs frontend-logs \
        migrate migrate-generate migrate-downgrade migrate-history \
        setup setup-status setup-admin setup-company setup-ai setup-complete \
        test test-backend test-frontend lint shell-backend shell-frontend \
        reset-db health

SHELL := /bin/bash

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

API_URL        ?= http://localhost:8080
ADMIN_USERNAME ?= admin
ADMIN_EMAIL    ?= admin@alcoabase.dev
ADMIN_PASSWORD ?= SecureP@ss2024!
ADMIN_FULLNAME ?= System Administrator
COMPANY_NAME   ?= AlcoaBase Dev
COMPANY_FRAMEWORK ?= GMP
AI_MODE        ?= mock

# ─────────────────────────────────────────────────────────────────────────────
# Docker Compose
# ─────────────────────────────────────────────────────────────────────────────

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

up: ## Start all services
	docker compose up -d

down: ## Stop all services
	docker compose down

rebuild: ## Rebuild and restart all services
	docker compose up -d --build

logs: ## Tail logs for all services
	docker compose logs -f

backend-logs: ## Tail backend logs
	docker compose logs -f backend

frontend-logs: ## Tail frontend logs
	docker compose logs -f frontend

shell-backend: ## Open a shell in the backend container
	docker compose exec backend bash

shell-frontend: ## Open a shell in the frontend container
	docker compose exec frontend sh

# ─────────────────────────────────────────────────────────────────────────────
# Database Migrations (Alembic)
# ─────────────────────────────────────────────────────────────────────────────

migrate: ## Run all pending Alembic migrations
	docker compose exec backend alembic upgrade head
	@echo "Ensuring Continuum tables exist..."
	docker compose exec backend python -c "exec(\"import asyncio\\nfrom sqlalchemy.orm import configure_mappers\\nfrom alcoabase.database import init_db, get_engine, Base\\nfrom alcoabase.models import *\\nconfigure_mappers()\\nasync def run():\\n    await init_db()\\n    e = get_engine()\\n    async with e.begin() as c:\\n        await c.run_sync(Base.metadata.create_all)\\n    print('  Done.')\\nasyncio.run(run())\")"

migrate-generate: ## Auto-generate a new migration (usage: make migrate-generate MSG="add foo")
	docker compose exec backend alembic revision --autogenerate -m "$(MSG)"

migrate-downgrade: ## Downgrade one migration step
	docker compose exec backend alembic downgrade -1

migrate-history: ## Show migration history
	docker compose exec backend alembic history --verbose

# ─────────────────────────────────────────────────────────────────────────────
# Setup Wizard
# ─────────────────────────────────────────────────────────────────────────────

setup-status: ## Check current setup wizard status
	@curl -s $(API_URL)/api/v1/setup/status | python3 -m json.tool

setup: ## Run full setup wizard (creates admin, company, configures AI, seeds demo data)
	@echo "═══════════════════════════════════════════════════════════════"
	@echo " AlcoaBase Setup Wizard"
	@echo "═══════════════════════════════════════════════════════════════"
	@echo ""
	@echo "Step 1/4: Creating root admin..."
	@RESPONSE=$$(curl -s -X POST $(API_URL)/api/v1/setup/admin \
		-H "Content-Type: application/json" \
		-d '{"username":"$(ADMIN_USERNAME)","email":"$(ADMIN_EMAIL)","password":"$(ADMIN_PASSWORD)","full_name":"$(ADMIN_FULLNAME)"}'); \
	TOKEN=$$(echo "$$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); t=d.get('access_token',''); print(t)" 2>/dev/null); \
	if [ -z "$$TOKEN" ]; then \
		echo "  ✗ Failed! Response:"; \
		echo "$$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$$RESPONSE"; \
		exit 1; \
	fi; \
	echo "  ✓ Admin created ($(ADMIN_USERNAME))"; \
	echo ""; \
	echo "Step 2/4: Creating company..."; \
	RESP2=$$(curl -s -X POST $(API_URL)/api/v1/setup/company \
		-H "Content-Type: application/json" \
		-H "Authorization: Bearer $$TOKEN" \
		-d '{"display_name":"$(COMPANY_NAME)","regulatory_framework":"$(COMPANY_FRAMEWORK)"}'); \
	echo "$$RESP2" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'company_id' in d or 'detail' in d" 2>/dev/null; \
	if echo "$$RESP2" | grep -q '"company_id"'; then \
		echo "  ✓ Company created ($(COMPANY_NAME))"; \
	else \
		echo "  ✗ Failed! Response:"; echo "$$RESP2" | python3 -m json.tool 2>/dev/null || echo "$$RESP2"; exit 1; \
	fi; \
	echo ""; \
	echo "Step 3/4: Configuring AI mode..."; \
	RESP3=$$(curl -s -X POST $(API_URL)/api/v1/setup/ai-mode \
		-H "Content-Type: application/json" \
		-H "Authorization: Bearer $$TOKEN" \
		-d '{"mode":"$(AI_MODE)"}'); \
	if echo "$$RESP3" | grep -q '"mode"'; then \
		echo "  ✓ AI mode set ($(AI_MODE))"; \
	else \
		echo "  ✗ Failed! Response:"; echo "$$RESP3" | python3 -m json.tool 2>/dev/null || echo "$$RESP3"; exit 1; \
	fi; \
	echo ""; \
	echo "Step 4/4: Completing setup..."; \
	RESP4=$$(curl -s -X POST $(API_URL)/api/v1/setup/complete \
		-H "Content-Type: application/json" \
		-H "Authorization: Bearer $$TOKEN" \
		-d '{"seed_demo_data":true}'); \
	if echo "$$RESP4" | grep -q '"message"'; then \
		echo "  ✓ Setup complete!"; \
	else \
		echo "  ✗ Failed! Response:"; echo "$$RESP4" | python3 -m json.tool 2>/dev/null || echo "$$RESP4"; exit 1; \
	fi; \
	echo ""; \
	echo "═══════════════════════════════════════════════════════════════"; \
	echo " Login credentials:"; \
	echo "   Username: $(ADMIN_USERNAME)"; \
	echo "   Password: $(ADMIN_PASSWORD)"; \
	echo "═══════════════════════════════════════════════════════════════"

# ─────────────────────────────────────────────────────────────────────────────
# Testing
# ─────────────────────────────────────────────────────────────────────────────

test: test-backend test-frontend ## Run all tests

test-backend: ## Run backend pytest tests
	cd src/backend && uv run pytest -q --tb=short

test-frontend: ## Run frontend vitest tests
	cd src/frontend && npx vitest run

lint: ## Run linters (backend + frontend)
	cd src/backend && uv run ruff check .
	cd src/frontend && npm run lint

# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────

reset-db: ## Drop and recreate the database (DESTRUCTIVE)
	@echo "⚠️  This will destroy all data. Press Ctrl+C to cancel."
	@sleep 3
	docker compose exec postgres psql -U alcoabase -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
	@echo "Database reset. Run 'make migrate' then 'make setup' to reinitialize."

health: ## Check health of all services
	@echo -n "Backend:    "; curl -sf $(API_URL)/health > /dev/null && echo "✓ OK" || echo "✗ DOWN"
	@echo -n "Frontend:   "; curl -sf http://localhost:3000/ > /dev/null && echo "✓ OK" || echo "✗ DOWN"
	@echo -n "PostgreSQL: "; docker compose exec -T postgres pg_isready -q && echo "✓ OK" || echo "✗ DOWN"
	@echo -n "Redis:      "; docker compose exec -T redis redis-cli -a changeme_redis ping 2>/dev/null | grep -q PONG && echo "✓ OK" || echo "✗ DOWN"
	@echo -n "OpenSearch: "; curl -sf http://localhost:9200/_cluster/health > /dev/null && echo "✓ OK" || echo "✗ DOWN"
