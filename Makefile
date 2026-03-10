.PHONY: help install dev test lint format clean build run docker-up docker-down migrate

# Default target
help:
	@echo "AI Gateway - Available commands:"
	@echo ""
	@echo "  install      Install Python dependencies"
	@echo "  dev          Run development server"
	@echo "  test         Run all tests"
	@echo "  test-cov     Run tests with coverage"
	@echo "  lint         Run linting checks"
	@echo "  format       Format code with ruff"
	@echo "  clean        Clean up generated files"
	@echo "  build        Build Docker image"
	@echo "  docker-up    Start all services with Docker Compose"
	@echo "  docker-down  Stop all Docker services"
	@echo "  migrate      Run database migrations"
	@echo "  migrate-new  Create a new migration"
	@echo ""

# Python environment
install:
	cd backend && pip install -e ".[dev]"

install-uv:
	cd backend && uv pip install -e ".[dev]"

# Development
dev:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Testing
test:
	cd backend && python -m pytest tests/ -v

test-cov:
	cd backend && python -m pytest tests/ -v --cov=app --cov-report=html --cov-report=term

test-unit:
	cd backend && python -m pytest tests/unit_tests/ -v

test-integration:
	cd backend && python -m pytest tests/integration_tests/ -v

# Code quality
lint:
	cd backend && ruff check .
	cd backend && mypy app/

format:
	cd backend && ruff format .

format-check:
	cd backend && ruff format --check .

# Cleanup
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov/ .coverage

# Docker
docker-build:
	docker build -t ai-gateway:latest backend/

docker-up:
	docker-compose -f deploy/docker/docker-compose.yaml up -d

docker-down:
	docker-compose -f deploy/docker/docker-compose.yaml down

docker-logs:
	docker-compose -f deploy/docker/docker-compose.yaml logs -f

# Database
migrate:
	cd backend && alembic upgrade head

migrate-down:
	cd backend && alembic downgrade -1

migrate-new:
	@read -p "Enter migration message: " msg; \
	cd backend && alembic revision --autogenerate -m "$$msg"

migrate-reset:
	cd backend && alembic downgrade base && alembic upgrade head

# Kubernetes
k8s-apply:
	kubectl apply -f deploy/k8s/

k8s-delete:
	kubectl delete -f deploy/k8s/

k8s-logs:
	kubectl logs -l app=ai-gateway -f

# Database setup (local)
db-setup:
	docker run -d --name ai-gateway-postgres \
		-e POSTGRES_USER=postgres \
		-e POSTGRES_PASSWORD=postgres \
		-e POSTGRES_DB=ai_gateway \
		-p 5432:5432 \
		postgres:16-alpine

	docker run -d --name ai-gateway-redis \
		-p 6379:6379 \
		redis:7-alpine

db-stop:
	docker stop ai-gateway-postgres ai-gateway-redis || true
	docker rm ai-gateway-postgres ai-gateway-redis || true

# Generate API key
generate-key:
	@python -c "from app.core.security import generate_api_key; print(generate_api_key())"
