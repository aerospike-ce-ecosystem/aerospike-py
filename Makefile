SHELL := /bin/bash

AEROSPIKE_HOST ?= 127.0.0.1
AEROSPIKE_PORT ?= 18710

RUNTIME ?= podman
BENCH_COUNT ?= 1000
BENCH_ROUNDS ?= 5
BENCH_CONCURRENCY ?= 50
BENCH_BATCH_GROUPS ?= 10
BENCH_SCENARIO ?= basic

NUMPY_BENCH_ROUNDS ?= 10
NUMPY_BENCH_CONCURRENCY ?= 50
NUMPY_BENCH_BATCH_GROUPS ?= 10

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

.PHONY: install
install: ## Install project dependencies via uv
	uv sync --group dev --group bench

.PHONY: build
build: install ## Build Rust extension locally (maturin develop)
	uv run maturin develop --release

# ---------------------------------------------------------------------------
# Aerospike Server
# ---------------------------------------------------------------------------

.PHONY: run-aerospike-ce
run-aerospike-ce: ## Start Aerospike CE container (RUNTIME=docker|podman)
	@if $(RUNTIME) ps --format '{{.Names}}' | grep -q '^aerospike$$'; then \
		echo "aerospike container is already running ($(RUNTIME))"; \
	else \
		$(RUNTIME) compose -f compose.local.yaml up -d; \
		echo "Waiting for Aerospike to start..."; \
		sleep 3; \
	fi

.PHONY: stop-aerospike-ce
stop-aerospike-ce: ## Stop and remove Aerospike CE container
	$(RUNTIME) compose -f compose.local.yaml down 2>/dev/null || true

# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------

# Common benchmark arguments
BENCH_ARGS = --count $(BENCH_COUNT) --rounds $(BENCH_ROUNDS) \
	--concurrency $(BENCH_CONCURRENCY) --batch-groups $(BENCH_BATCH_GROUPS) \
	--host $(AEROSPIKE_HOST) --port $(AEROSPIKE_PORT)

.PHONY: run-benchmark-report
run-benchmark-report: build run-aerospike-ce ## Run benchmark + generate JSON report (BENCH_SCENARIO=basic|all, numpy auto-included with all)
	AEROSPIKE_HOST=$(AEROSPIKE_HOST) AEROSPIKE_PORT=$(AEROSPIKE_PORT) \
	uv run python benchmark/bench_compare.py \
		$(BENCH_ARGS) --scenario $(BENCH_SCENARIO) --report; \
	$(MAKE) stop-aerospike-ce

# ---------------------------------------------------------------------------
# Lint & Format
# ---------------------------------------------------------------------------

.PHONY: lint
lint: ## Run all linters (ruff + clippy)
	uv run ruff check src/ tests/ benchmark/
	uv run ruff format --check src/ tests/ benchmark/
	cargo clippy --manifest-path rust/Cargo.toml --features otel -- -D warnings

.PHONY: fmt
fmt: ## Auto-format Python (ruff) and Rust (cargo fmt)
	uv run ruff format src/ tests/ benchmark/
	uv run ruff check --fix src/ tests/ benchmark/
	cargo fmt --manifest-path rust/Cargo.toml

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

.PHONY: test-unit
test-unit: build ## Run unit tests (no server needed)
	uv run pytest tests/unit/ -v

.PHONY: test-integration
test-integration: build run-aerospike-ce ## Run integration tests
	uvx --with tox-uv tox -e integration

.PHONY: test-concurrency
test-concurrency: build run-aerospike-ce ## Run concurrency/thread-safety tests
	uvx --with tox-uv tox -e concurrency

.PHONY: test-compat
test-compat: build run-aerospike-ce ## Run compatibility tests (vs official C client)
	uvx --with tox-uv tox -e compat

.PHONY: test-all
test-all: build run-aerospike-ce ## Run all tests
	uvx --with tox-uv tox -e all

.PHONY: test-matrix
test-matrix: build ## Run unit tests across all Python versions
	uvx --with tox-uv tox

.PHONY: coverage
coverage: build ## Generate test coverage report
	uv run pytest tests/unit/ --cov=aerospike_py --cov-report=term --cov-report=html
	@echo "Coverage report: htmlcov/index.html"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

.PHONY: check
check: ## Compile check without building (fast)
	cargo check --manifest-path rust/Cargo.toml --features otel

.PHONY: typecheck
typecheck: ## Run type checker (pyright)
	uv run pyright src/aerospike_py

.PHONY: validate
validate: fmt lint typecheck test-unit ## Run full validation (format, lint, typecheck, unit tests)

.PHONY: dev-build
dev-build: install ## Fast debug build without release optimizations
	uv run maturin develop

.PHONY: pre-commit-install
pre-commit-install: ## Install pre-commit hooks
	pre-commit install

# ---------------------------------------------------------------------------
# Documentation
# ---------------------------------------------------------------------------

.PHONY: docs-build
docs-build: ## Build Docusaurus docs site
	cd docs && npm run build

.PHONY: docs-serve
docs-serve: ## Serve built docs locally (run docs-build first)
	cd docs && npm run serve

.PHONY: docs-start
docs-start: ## Start Docusaurus dev server with hot reload
	cd docs && npm start

.PHONY: docs-version
docs-version: ## Create a new docs version (usage: make docs-version VERSION=0.1.0)
	@test -n "$(VERSION)" || (echo "ERROR: VERSION required. Usage: make docs-version VERSION=0.1.0" && exit 1)
	bash docs/scripts/create-version.sh $(VERSION)

.PHONY: clean
clean: ## Remove venv, build artifacts, and docs build cache
	rm -rf .venv target/ dist/ *.egg-info .pytest_cache htmlcov/ .coverage
	rm -rf docs/build docs/.docusaurus
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
