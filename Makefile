SHELL := /bin/bash

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

AEROSPIKE_HOST ?= 127.0.0.1
AEROSPIKE_PORT ?= 3000

RUNTIME ?= docker
BENCH_COUNT ?= 1000
BENCH_ROUNDS ?= 5
BENCH_CONCURRENCY ?= 50

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

$(VENV)/bin/activate:
	python3 -m venv $(VENV)

.PHONY: install
install: $(VENV)/bin/activate ## Install dependencies
	$(PIP) install --upgrade pip
	$(PIP) install aerospike-py aerospike pytest pytest-asyncio

# ---------------------------------------------------------------------------
# Aerospike Server
# ---------------------------------------------------------------------------

.PHONY: run-aerospike-ce
run-aerospike-ce: ## Start Aerospike CE container (RUNTIME=docker|podman)
	@if $(RUNTIME) ps --format '{{.Names}}' | grep -q '^aerospike$$'; then \
		echo "aerospike container is already running ($(RUNTIME))"; \
	else \
		$(RUNTIME) run -d --name aerospike \
			-p 3000:3000 -p 3001:3001 -p 3002:3002 \
			--shm-size=1g \
			-e "NAMESPACE=test" \
			-e "DEFAULT_TTL=2592000" \
			-v $(CURDIR)/scripts/aerospike.template.conf:/etc/aerospike/aerospike.template.conf \
			aerospike:ce-8.1.0.3_1; \
		echo "Waiting for Aerospike to start..."; \
		sleep 3; \
	fi

.PHONY: stop-aerospike-ce
stop-aerospike-ce: ## Stop and remove Aerospike CE container
	$(RUNTIME) rm -f aerospike 2>/dev/null || true

# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------

.PHONY: run-benchmark
run-benchmark: install run-aerospike-ce ## Run benchmark (COUNT, ROUNDS, CONCURRENCY configurable)
	AEROSPIKE_HOST=$(AEROSPIKE_HOST) AEROSPIKE_PORT=$(AEROSPIKE_PORT) \
	$(PYTHON) benchmark/bench_compare.py \
		--count $(BENCH_COUNT) \
		--rounds $(BENCH_ROUNDS) \
		--concurrency $(BENCH_CONCURRENCY) \
		--host $(AEROSPIKE_HOST) \
		--port $(AEROSPIKE_PORT)

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

.PHONY: test-unit
test-unit: install ## Run unit tests (no server needed)
	uvx --with tox-uv tox -e py312

.PHONY: test-integration
test-integration: install run-aerospike-ce ## Run integration tests
	uvx --with tox-uv tox -e integration

.PHONY: test-all
test-all: install run-aerospike-ce ## Run all tests
	uvx --with tox-uv tox -e all

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

.PHONY: clean
clean: ## Remove venv and build artifacts
	rm -rf $(VENV) target/ dist/ *.egg-info

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
