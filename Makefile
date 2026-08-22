# SuperGuard Makefile - Development Commands

.PHONY: help dev build up down logs test lint clean

# Default target
help:
	@echo "SuperGuard Development Commands"
	@echo ""
	@echo "Development:"
	@echo "  make dev          - Start development environment (all services)"
	@echo "  make dev-api      - Start API only (with hot reload)"
	@echo "  make dev-dashboard - Start Dashboard only (with hot reload)"
	@echo ""
	@echo "Docker:"
	@echo "  make build        - Build all Docker images"
	@echo "  make up           - Start all containers (production mode)"
	@echo "  make down         - Stop all containers"
	@echo "  make logs         - View container logs"
	@echo "  make restart      - Restart all containers"
	@echo ""
	@echo "Database:"
	@echo "  make migrate      - Run database migrations"
	@echo "  make seed         - Seed database with test data"
	@echo ""
	@echo "Testing:"
	@echo "  make test         - Run all tests"
	@echo "  make test-api     - Run API tests only"
	@echo "  make test-e2e     - Run end-to-end tests"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint         - Run linters (ruff, mypy)"
	@echo "  make format       - Format code (ruff, prettier)"
	@echo ""
	@echo "Utilities:"
	@echo "  make clean        - Clean build artifacts"
	@echo "  make reset        - Full reset (down + clean + up)"
	@echo "  make backup       - Backup database"
	@echo "  make restore      - Restore database"

# ============================================================================
# Development
# ============================================================================
dev:
	docker compose up -d postgres redis mediamtx
	@echo "Waiting for services to be healthy..."
	@sleep 5
	@echo "Starting API in background..."
	cd superguard-api && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 3001 &
	@echo "Starting Dashboard in background..."
	cd superguard-dashboard && npm run dev &
	@echo ""
	@echo "Development environment started!"
	@echo "  API:      http://localhost:3001"
	@echo "  Dashboard: http://localhost:3000"
	@echo "  MediaMTX: http://localhost:8888"

dev-api:
	cd superguard-api && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 3001

dev-dashboard:
	cd superguard-dashboard && npm run dev

# ============================================================================
# Docker
# ============================================================================
build:
	docker compose build --parallel

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

restart:
	docker compose restart

# ============================================================================
# Database
# ============================================================================
migrate:
	docker compose exec api alembic upgrade head

seed:
	docker compose exec api python scripts/seed_database.py

# ============================================================================
# Testing
# ============================================================================
test:
	docker compose -f docker-compose.yml -f docker-compose.test.yml up --abort-on-container-exit --exit-code-from test

test-api:
	docker compose exec api python -m pytest tests/ -v

test-e2e:
	docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm cypress

# ============================================================================
# Code Quality
# ============================================================================
lint:
	cd superguard-api && ruff check . && mypy app --ignore-missing-imports
	cd superguard-dashboard && npm run lint || true

format:
	cd superguard-api && ruff format .
	cd superguard-dashboard && npm run format

# ============================================================================
# Utilities
# ============================================================================
clean:
	docker compose down -v --remove-orphans
	docker system prune -f
	rm -rf superguard-api/__pycache__ superguard-api/.pytest_cache
	rm -rf superguard-dashboard/node_modules superguard-dashboard/dist

reset: down clean up

backup:
	docker compose exec postgres pg_dump -U superguard superguard > backup_$$(date +%Y%m%d_%H%M%S).sql

restore:
	@read -p "Enter backup file: " file; \
	docker compose exec -T postgres psql -U superguard superguard < $$file

# ============================================================================
# Production
# ============================================================================
prod-up:
	docker compose --profile production up -d

prod-down:
	docker compose --profile production down

prod-logs:
	docker compose --profile production logs -f

# ============================================================================
# SSL Certificates (Let's Encrypt via certbot)
# ============================================================================
ssl-generate:
	@mkdir -p ssl
	docker run --rm -it \
		-v $$(pwd)/ssl:/etc/letsencrypt \
		-v $$(pwd)/ssl:/var/lib/letsencrypt \
		certbot/certbot certonly --standalone \
		-d your-domain.com

ssl-renew:
	docker run --rm -it \
		-v $$(pwd)/ssl:/etc/letsencrypt \
		-v $$(pwd)/ssl:/var/lib/letsencrypt \
		certbot/certbot renew