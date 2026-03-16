.PHONY: install fmt lint typecheck test coverage validate clean help

install: ## Install project dependencies
	uv sync --group dev

fmt: ## Auto-format code (ruff)
	uv run ruff format .
	uv run ruff check --fix .

lint: ## Run linters (ruff)
	uv run ruff check .
	uv run ruff format --check .

typecheck: ## Run type checker (pyright)
	uv run pyright src/

test: ## Run tests
	uv run pytest -v

coverage: ## Generate test coverage report
	uv run pytest --cov=aaa --cov-report=term --cov-report=html
	@echo "Coverage report: htmlcov/index.html"

validate: fmt lint typecheck test ## Full validation pipeline

clean: ## Remove build artifacts
	rm -rf .venv dist/ *.egg-info .pytest_cache htmlcov/ .coverage .ruff_cache .pyright
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
