# =============================================================================
# Tenancy Service - Production-Grade Makefile
# =============================================================================
# 
# Available commands:
#   make help          - Show this help
#   make install       - Install dependencies
#   make dev           - Run development server
#   make test          - Run all tests
#   make lint          - Run code linting
#   make format        - Format code
#   make db-*          - Database operations
#   make docker-*      - Docker operations
#   make deploy-*      - Deployment operations
#
# =============================================================================

SHELL := /bin/bash
.DEFAULT_GOAL := help
.PHONY: help install dev test lint format clean build docker-* db-* deploy-*

# Colors for output
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[0;33m
BLUE := \033[0;34m
NC := \033[0m # No Color

# Project configuration
PROJECT_NAME := tenancy_service
PYTHON_VERSION := 3.12
VENV_NAME := .venv

# Detect platform
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Linux)
    PLATFORM := linux
endif
ifeq ($(UNAME_S),Darwin)
    PLATFORM := macos
endif

# =============================================================================
# Help & Information
# =============================================================================

help: ## Show this help message
	@echo -e "$(BLUE)$(PROJECT_NAME) - Production-Grade Tenancy Service$(NC)"
	@echo -e "================================================================"
	@echo -e ""
	@echo -e "$(GREEN)Available commands:$(NC)"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  $(YELLOW)%-20s$(NC) %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo -e ""
	@echo -e "$(GREEN)Quick start:$(NC)"
	@echo -e "  1. make install      # Install dependencies"
	@echo -e "  2. make db-setup     # Setup database"
	@echo -e "  3. make dev          # Start development server"

info: ## Show project information
	@echo -e "$(BLUE)Project Information$(NC)"
	@echo -e "Name: $(PROJECT_NAME)"
	@echo -e "Python: $(PYTHON_VERSION)"
	@echo -e "Platform: $(PLATFORM)"
	@echo -e "Virtual Env: $(VENV_NAME)"
	@echo -e "Current directory: $(PWD)"

# =============================================================================
# Environment & Dependencies
# =============================================================================

install: ## Install all dependencies
	@echo -e "$(GREEN)Installing dependencies...$(NC)"
	@if [ ! -d "$(VENV_NAME)" ]; then \
		echo -e "$(YELLOW)Creating virtual environment...$(NC)"; \
		uv venv $(VENV_NAME); \
	fi
	@echo -e "$(YELLOW)Installing Python packages...$(NC)"
	@uv pip install -r requirements.txt
	@uv pip install -e .
	@echo -e "$(GREEN)Dependencies installed successfully!$(NC)"

install-dev: ## Install development dependencies
	@echo -e "$(GREEN)Installing development dependencies...$(NC)"
	@uv pip install pytest pytest-asyncio pytest-cov black isort flake8 mypy pre-commit
	@pre-commit install
	@echo -e "$(GREEN)Development environment ready!$(NC)"

install-prod: ## Install production dependencies only
	@echo -e "$(GREEN)Installing production dependencies...$(NC)"
	@uv pip install -r requirements.txt --no-dev
	@echo -e "$(GREEN)Production dependencies installed!$(NC)"

clean: ## Clean up generated files and caches
	@echo -e "$(YELLOW)Cleaning up...$(NC)"
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete
	@find . -type f -name "*.pyo" -delete
	@find . -type f -name "*.pyd" -delete
	@find . -type f -name ".coverage" -delete
	@find . -type f -name "*.coverage" -delete
	@rm -rf .pytest_cache/ .mypy_cache/ .ruff_cache/ .coverage htmlcov/ dist/ build/ *.egg-info
	@rm -rf .kiro/ .venv/
	@echo -e "$(GREEN)Cleanup completed!$(NC)"

# =============================================================================
# Development & Testing
# =============================================================================

dev: ## Start development server with auto-reload
	@echo -e "$(GREEN)Starting development server...$(NC)"
	@echo -e "$(BLUE)Server will be available at: http://localhost:8000$(NC)"
	@echo -e "$(BLUE)API docs available at: http://localhost:8000/docs$(NC)"
	@uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-debug: ## Start development server with debug logging
	@echo -e "$(GREEN)Starting development server in debug mode...$(NC)"
	@export DEBUG=true && source $(VENV_NAME)/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --log-level debug

test: ## Run all tests
	@echo -e "$(GREEN)Running tests...$(NC)"
	@uv run python -m pytest tests/ -v --tb=short

test-cov: ## Run tests with coverage report
	@echo -e "$(GREEN)Running tests with coverage...$(NC)"
	@uv run python -m pytest tests/ -v --cov=. --cov-report=html --cov-report=term-missing

test-unit: ## Run unit tests only
	@echo -e "$(GREEN)Running unit tests...$(NC)"
	@uv run python -m pytest tests/unit/ -v

test-integration: ## Run integration tests only
	@echo -e "$(GREEN)Running integration tests...$(NC)"
	@uv run python -m pytest tests/integration/ -v

test-watch: ## Run tests in watch mode
	@echo -e "$(GREEN)Running tests in watch mode...$(NC)"
	@uv run python -m pytest tests/ -f

# =============================================================================
# Code Quality
# =============================================================================

lint: ## Run all linting checks
	@echo -e "$(GREEN)Running linting checks...$(NC)"
	@uv run flake8 app/ tests/
	@uv run mypy app/

format: ## Format code with black and isort
	@echo -e "$(GREEN)Formatting code...$(NC)"
	@uv run black app/ tests/
	@uv run isort app/ tests/

format-check: ## Check code formatting without making changes
	@echo -e "$(GREEN)Checking code formatting...$(NC)"
	@uv run black --check app/ tests/
	@uv run isort --check-only app/ tests/

check: lint format-check test ## Run all quality checks

# =============================================================================
# Database Operations
# =============================================================================

db-setup: ## Setup database and run migrations
	@echo -e "$(GREEN)Setting up database...$(NC)"
	@uv run alembic upgrade head
	@echo -e "$(GREEN)Database setup completed!$(NC)"

db-migrate: ## Create new database migration
	@echo -e "$(GREEN)Creating database migration...$(NC)"
	@read -p "Enter migration message: " message; \
	uv run alembic revision --autogenerate -m "$$message"

db-upgrade: ## Run database migrations (upgrade to head)
	@echo -e "$(GREEN)Running database migrations...$(NC)"
	@uv run alembic upgrade head

db-downgrade: ## Downgrade database by one migration
	@echo -e "$(YELLOW)Downgrading database...$(NC)"
	@uv run alembic downgrade -1

db-reset: ## Reset database (WARNING: destroys all data)
	@echo -e "$(RED)WARNING: This will destroy all data!$(NC)"
	@read -p "Are you sure? (y/N): " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		uv run alembic downgrade base && uv run alembic upgrade head; \
		echo -e "$(GREEN)Database reset completed!$(NC)"; \
	else \
		echo -e "$(YELLOW)Database reset cancelled.$(NC)"; \
	fi

db-seed: ## Seed database with sample data
	@echo -e "$(GREEN)Seeding database...$(NC)"
	@uv run python scripts/seed_database.py

# =============================================================================
# Docker Operations
# =============================================================================

docker-build: ## Build Docker image
	@echo -e "$(GREEN)Building Docker image...$(NC)"
	@docker build -t $(PROJECT_NAME):latest .
	@echo -e "$(GREEN)Docker image built: $(PROJECT_NAME):latest$(NC)"

docker-run: ## Run application in Docker container
	@echo -e "$(GREEN)Running Docker container...$(NC)"
	@docker run -p 8000:8000 --env-file .env $(PROJECT_NAME):latest

docker-dev: ## Run development environment with Docker Compose
	@echo -e "$(GREEN)Starting development environment...$(NC)"
	@docker-compose -f docker-compose.dev.yml up -d
	@echo -e "$(BLUE)Services started:$(NC)"
	@echo -e "  - API: http://localhost:8000"
	@echo -e "  - PostgreSQL: localhost:5432"
	@echo -e "  - Redis: localhost:6379"

docker-prod: ## Run production environment with Docker Compose
	@echo -e "$(GREEN)Starting production environment...$(NC)"
	@docker-compose -f docker-compose.prod.yml up -d

docker-stop: ## Stop all Docker containers
	@echo -e "$(YELLOW)Stopping Docker containers...$(NC)"
	@docker-compose -f docker-compose.dev.yml down || true
	@docker-compose -f docker-compose.prod.yml down || true

docker-logs: ## Show Docker container logs
	@docker-compose -f docker-compose.dev.yml logs -f

docker-clean: ## Clean Docker images and containers
	@echo "$(YELLOW)Cleaning Docker resources...$(NC)"
	@docker system prune -f
	@docker image prune -f

# =============================================================================
# Deployment
# =============================================================================

build: ## Build application for production
	@echo -e "$(GREEN)Building application...$(NC)"
	@uv run python -m build
	@echo -e "$(GREEN)Build completed!$(NC)"

deploy-staging: ## Deploy to staging environment
	@echo -e "$(GREEN)Deploying to staging...$(NC)"
	@echo -e "$(YELLOW)TODO: Implement staging deployment$(NC)"

deploy-prod: ## Deploy to production environment
	@echo -e "$(GREEN)Deploying to production...$(NC)"
	@echo -e "$(YELLOW)TODO: Implement production deployment$(NC)"

# =============================================================================
# Utilities
# =============================================================================

shell: ## Open Python shell with application context
	@echo -e "$(GREEN)Opening Python shell...$(NC)"
	@uv run python

logs: ## Tail application logs
	@echo -e "$(GREEN)Showing application logs...$(NC)"
	@tail -f logs/*.log 2>/dev/null || echo -e "$(YELLOW)No log files found$(NC)"

health: ## Check application health
	@echo -e "$(GREEN)Checking application health...$(NC)"
	@curl -f http://localhost:8000/health || echo -e "$(RED)Service not responding$(NC)"

metrics: ## Show application metrics
	@echo -e "$(GREEN)Application metrics:$(NC)"
	@curl -s http://localhost:9090/metrics || echo -e "$(RED)Metrics not available$(NC)"

docs: ## Generate and serve documentation
	@echo -e "$(GREEN)Generating documentation...$(NC)"
	@echo -e "$(BLUE)API documentation: http://localhost:8000/docs$(NC)"
	@echo -e "$(BLUE)ReDoc documentation: http://localhost:8000/redoc$(NC)"

# =============================================================================
# Environment Setup
# =============================================================================

env-create: ## Create .env file from template
	@if [ ! -f .env ]; then \
		echo -e "$(GREEN)Creating .env file...$(NC)"; \
		cp .env.example .env 2>/dev/null || echo -e "$(YELLOW)No .env.example found$(NC)"; \
		echo -e "$(BLUE)Please edit .env file with your configuration$(NC)"; \
	else \
		echo -e "$(YELLOW).env file already exists$(NC)"; \
	fi

env-check: ## Validate environment configuration
	@echo -e "$(GREEN)Validating environment...$(NC)"
	@uv run python -c "from app.infrastructure.config.settings import get_settings; settings = get_settings(); print('✅ Configuration valid')"

# =============================================================================
# Monitoring & Observability
# =============================================================================

monitor: ## Start monitoring dashboard
	@echo -e "$(GREEN)Starting monitoring...$(NC)"
	@echo -e "$(BLUE)Grafana: http://localhost:3000$(NC)"
	@echo -e "$(BLUE)Prometheus: http://localhost:9090$(NC)"

backup: ## Backup database
	@echo -e "$(GREEN)Creating database backup...$(NC)"
	@timestamp=$$(date +%Y%m%d_%H%M%S); \
	pg_dump $(DATABASE_URL) > backups/backup_$$timestamp.sql; \
	echo -e "$(GREEN)Backup created: backups/backup_$$timestamp.sql$(NC)"

restore: ## Restore database from backup
	@echo -e "$(YELLOW)Available backups:$(NC)"
	@ls -la backups/*.sql 2>/dev/null || echo "No backups found"
	@read -p "Enter backup filename: " backup; \
	if [ -f "backups/$$backup" ]; then \
		psql $(DATABASE_URL) < backups/$$backup; \
		echo -e "$(GREEN)Database restored from $$backup$(NC)"; \
	else \
		echo -e "$(RED)Backup file not found: $$backup$(NC)"; \
	fi