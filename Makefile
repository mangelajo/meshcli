.PHONY: help sync build test lint format clean publish install dev-install run

# Default target
help: ## Show this help message
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

sync: ## Sync dependencies and create virtual environment
	uv sync --dev

build: ## Build the package
	uv build

test: ## Run tests
	uv run pytest

lint: ## Run linting checks
	uv run ruff check meshctl tests

format: ## Format code with black
	uv run black meshctl tests

fix: ## Fix linting issues automatically and format code
	uv run ruff check --fix meshctl tests
	uv run black meshctl tests

format-check: ## Check code formatting without making changes
	uv run black --check meshctl tests

install: ## Install the package in development mode
	uv pip install -e .

dev-install: sync ## Install development dependencies (alias for sync)

run: ## Run the CLI tool
	uv run meshctl

clean: ## Clean build artifacts and cache
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

publish: build ## Build and publish to PyPI
	uv publish

publish-test: build ## Build and publish to TestPyPI
	uv publish --index-url https://test.pypi.org/simple/

check: lint format-check test ## Run all checks (lint, format-check, test)

all: sync check build ## Run sync, all checks, and build
