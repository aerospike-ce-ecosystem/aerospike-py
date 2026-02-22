SHELL := /bin/bash

AEROSPIKE_HOST ?= 127.0.0.1
AEROSPIKE_PORT ?= 18710

RUNTIME ?= podman
BENCH_COUNT ?= 5000
BENCH_ROUNDS ?= 20
BENCH_CONCURRENCY ?= 50
BENCH_BATCH_GROUPS ?= 10

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

.PHONY: run-benchmark
run-benchmark: build run-aerospike-ce ## Run benchmark with local build (COUNT, ROUNDS, CONCURRENCY configurable)
	AEROSPIKE_HOST=$(AEROSPIKE_HOST) AEROSPIKE_PORT=$(AEROSPIKE_PORT) \
	uv run python benchmark/bench_compare.py \
		--count $(BENCH_COUNT) \
		--rounds $(BENCH_ROUNDS) \
		--concurrency $(BENCH_CONCURRENCY) \
		--batch-groups $(BENCH_BATCH_GROUPS) \
		--host $(AEROSPIKE_HOST) \
		--port $(AEROSPIKE_PORT); \
	$(MAKE) stop-aerospike-ce

.PHONY: run-benchmark-large
run-benchmark-large: build run-aerospike-ce ## Run large-scale benchmark (100K ops)
	AEROSPIKE_HOST=$(AEROSPIKE_HOST) AEROSPIKE_PORT=$(AEROSPIKE_PORT) \
	uv run python benchmark/bench_compare.py \
		--count 100000 \
		--rounds 5 \
		--concurrency $(BENCH_CONCURRENCY) \
		--batch-groups $(BENCH_BATCH_GROUPS) \
		--host $(AEROSPIKE_HOST) \
		--port $(AEROSPIKE_PORT); \
	$(MAKE) stop-aerospike-ce

.PHONY: run-benchmark-report
run-benchmark-report: build run-aerospike-ce ## Run benchmark and generate docs report (JSON + charts)
	AEROSPIKE_HOST=$(AEROSPIKE_HOST) AEROSPIKE_PORT=$(AEROSPIKE_PORT) \
	uv run python benchmark/bench_compare.py \
		--count $(BENCH_COUNT) \
		--rounds $(BENCH_ROUNDS) \
		--concurrency $(BENCH_CONCURRENCY) \
		--batch-groups $(BENCH_BATCH_GROUPS) \
		--host $(AEROSPIKE_HOST) \
		--port $(AEROSPIKE_PORT) \
		--report; \
	$(MAKE) stop-aerospike-ce

.PHONY: run-numpy-benchmark
run-numpy-benchmark: build run-aerospike-ce ## Run numpy batch benchmark (dict vs numpy comparison)
	uv run python benchmark/bench_batch_numpy.py \
		--scenario all --rounds $(NUMPY_BENCH_ROUNDS) \
		--concurrency $(NUMPY_BENCH_CONCURRENCY) \
		--batch-groups $(NUMPY_BENCH_BATCH_GROUPS) \
		--host $(AEROSPIKE_HOST) --port $(AEROSPIKE_PORT); \
	$(MAKE) stop-aerospike-ce

.PHONY: run-numpy-benchmark-report
run-numpy-benchmark-report: build run-aerospike-ce ## Run numpy batch benchmark and generate report
	uv run python benchmark/bench_batch_numpy.py \
		--scenario all --rounds $(NUMPY_BENCH_ROUNDS) \
		--concurrency $(NUMPY_BENCH_CONCURRENCY) \
		--batch-groups $(NUMPY_BENCH_BATCH_GROUPS) \
		--host $(AEROSPIKE_HOST) --port $(AEROSPIKE_PORT) --report; \
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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Documentation
# ---------------------------------------------------------------------------

.PHONY: docs-version
docs-version: ## Create a new docs version (usage: make docs-version VERSION=0.1.0)
	@test -n "$(VERSION)" || (echo "ERROR: VERSION required. Usage: make docs-version VERSION=0.1.0" && exit 1)
	bash docs/scripts/create-version.sh $(VERSION)

.PHONY: clean
clean: ## Remove venv and build artifacts
	rm -rf .venv target/ dist/ *.egg-info

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
