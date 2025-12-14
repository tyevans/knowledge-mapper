# Knowledge Mapper Makefile
# Provides common development and testing commands

.PHONY: help docker-up docker-down docker-logs docker-reset \
        test test-api test-ui test-debug test-report test-install \
        backend-shell frontend-shell keycloak-setup keycloak-wait \
        clear-rate-limits setup ci-test

# Default target
.DEFAULT_GOAL := help

# Directory paths
PLAYWRIGHT_DIR := playwright
SCRIPTS_DIR := scripts

# Colors for output
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[1;33m
BLUE := \033[0;34m
NC := \033[0m

# Status symbols
CHECK := [OK]
CROSS := [FAIL]
INFO := [INFO]

# ============================================
# Help
# ============================================

help: ## Show this help message
	@echo ''
	@echo 'Knowledge Mapper - Development Commands'
	@echo ''
	@echo 'Docker Commands:'
	@grep -E '^docker-[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ''
	@echo 'Testing Commands:'
	@grep -E '^test[a-zA-Z_-]*:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ''
	@echo 'Setup Commands:'
	@grep -E '^(setup|keycloak-setup|keycloak-wait):.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ''
	@echo 'Shell Access:'
	@grep -E '^[a-zA-Z_-]+-shell:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ''
	@echo 'Redis Commands:'
	@grep -E '^clear-[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ''
	@echo 'CI Commands:'
	@grep -E '^ci-[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ''

# ============================================
# Docker Commands
# ============================================

docker-up: ## Start all Docker services
	./$(SCRIPTS_DIR)/docker-dev.sh up

docker-down: ## Stop all Docker services
	./$(SCRIPTS_DIR)/docker-dev.sh down

docker-logs: ## View Docker logs (use: make docker-logs SERVICE=backend)
	@if [ -n "$(SERVICE)" ]; then \
		./$(SCRIPTS_DIR)/docker-dev.sh logs $(SERVICE); \
	else \
		./$(SCRIPTS_DIR)/docker-dev.sh logs; \
	fi

docker-reset: ## Full clean restart of Docker services
	./$(SCRIPTS_DIR)/docker-dev.sh reset

# ============================================
# Shell Access
# ============================================

backend-shell: ## Open shell in backend container
	./$(SCRIPTS_DIR)/docker-dev.sh shell backend

frontend-shell: ## Open shell in frontend container
	./$(SCRIPTS_DIR)/docker-dev.sh shell frontend

# ============================================
# Keycloak
# ============================================

keycloak-setup: ## Run Keycloak realm setup script
	./keycloak/setup-realm.sh

keycloak-wait: ## Wait for Keycloak to be ready
	@echo "Waiting for Keycloak to be ready..."
	@until curl -sf http://localhost:8080/health/ready > /dev/null 2>&1; do \
		echo "  Keycloak not ready, waiting..."; \
		sleep 5; \
	done
	@echo "Keycloak is ready!"

# ============================================
# Redis Commands
# ============================================

clear-rate-limits: ## Clear rate limit keys from Redis
	docker exec knowledge-mapper-redis redis-cli -a knowledge_mapper_redis_pass FLUSHDB

# ============================================
# Playwright Testing Commands
# ============================================

test: ## Run all Playwright tests
	cd $(PLAYWRIGHT_DIR) && npm test

test-api: ## Run API tests only
	cd $(PLAYWRIGHT_DIR) && npm run test:api

test-ui: ## Run tests in interactive UI mode
	cd $(PLAYWRIGHT_DIR) && npm run test:ui

test-debug: ## Run tests in debug mode
	cd $(PLAYWRIGHT_DIR) && npm run test:debug

test-report: ## Show Playwright test report
	cd $(PLAYWRIGHT_DIR) && npm run report

test-install: ## Install Playwright dependencies
	cd $(PLAYWRIGHT_DIR) && npm install

# ============================================
# Full Setup Commands
# ============================================

setup: ## Initial project setup (install deps, start services, setup keycloak)
	@echo "Installing Playwright dependencies..."
	$(MAKE) test-install
	@echo ""
	@echo "Starting Docker services..."
	$(MAKE) docker-up
	@echo ""
	@echo "Waiting for services..."
	$(MAKE) keycloak-wait
	@echo ""
	@echo "Setting up Keycloak realm..."
	$(MAKE) keycloak-setup
	@echo ""
	@echo "Setup complete! Run 'make test-api' to verify."

# ============================================
# CI Commands
# ============================================

ci-test: ## Run tests in CI mode
	cd $(PLAYWRIGHT_DIR) && CI=true npm test
