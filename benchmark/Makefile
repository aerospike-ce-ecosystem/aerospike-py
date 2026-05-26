RUNTIME ?= podman
PYTHON ?= 3.11
HOST ?= 127.0.0.1
PORT ?= 8000
AEROSPIKE_HOST ?= 127.0.0.1
AEROSPIKE_PORT ?= 18710
SEED_COUNT ?= 10000
SCENARIO ?= s1
CONCURRENCY ?= 10
DURATION ?= 30s
BATCH_SIZE ?= 50

.PHONY: help sync up down seed serve-py serve-official bench-s1-py bench-s1-official bench-s1 report clean fmt lint

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

sync: ## Install deps in this project's .venv (does not affect parent venv)
	uv sync --python $(PYTHON)

up: ## Start Aerospike CE container (port $(AEROSPIKE_PORT))
	$(RUNTIME) compose -f compose.yaml up -d
	@echo "Waiting for Aerospike to be healthy..."
	@for i in 1 2 3 4 5 6 7 8 9 10; do \
		if $(RUNTIME) exec aerospike-bench asinfo -v status 2>/dev/null | grep -q ok; then \
			echo "Aerospike ready."; exit 0; \
		fi; \
		sleep 2; \
	done; \
	echo "Aerospike did not become healthy in 20s"; exit 1

down: ## Stop and remove the Aerospike container
	$(RUNTIME) compose -f compose.yaml down -v

seed: ## Load $(SEED_COUNT) deterministic records into test/bench
	uv run python -m app.seed --count $(SEED_COUNT) --host $(AEROSPIKE_HOST) --port $(AEROSPIKE_PORT)

serve-py: ## Run FastAPI with aerospike-py AsyncClient
	CLIENT=py AEROSPIKE_HOST=$(AEROSPIKE_HOST) AEROSPIKE_PORT=$(AEROSPIKE_PORT) \
		uv run uvicorn app.main:app --host $(HOST) --port $(PORT) --workers 1

serve-official: ## Run FastAPI with official client + asyncio.to_thread
	CLIENT=official AEROSPIKE_HOST=$(AEROSPIKE_HOST) AEROSPIKE_PORT=$(AEROSPIKE_PORT) \
		uv run uvicorn app.main:app --host $(HOST) --port $(PORT) --workers 1

bench-s1-py: ## Run oha against S1 with aerospike-py (server must be serve-py)
	bash loadtest/run_oha.sh s1 py $(CONCURRENCY) $(DURATION) $(BATCH_SIZE)

bench-s1-official: ## Run oha against S1 with official (server must be serve-official)
	bash loadtest/run_oha.sh s1 official $(CONCURRENCY) $(DURATION) $(BATCH_SIZE)

bench-s1: ## End-to-end: start/stop both servers and bench S1
	bash loadtest/bench_matrix.sh s1 $(CONCURRENCY) $(DURATION) $(BATCH_SIZE)

bench: ## End-to-end bench for SCENARIO=<s1|s2|s3|s4_gather|s4_single|s5>
	bash loadtest/bench_matrix.sh $(SCENARIO) $(CONCURRENCY) $(DURATION) $(BATCH_SIZE)

bench-all: ## Bench all 6 scenario variants sequentially (py vs official for each)
	@set -e; for s in s1 s2 s3 s4_gather s4_single s5; do \
		echo; echo "===== scenario $$s ====="; \
		bash loadtest/bench_matrix.sh $$s $(CONCURRENCY) $(DURATION) $(BATCH_SIZE); \
	done

report: ## Render a markdown comparison table from results/
	uv run python -m loadtest.report

fmt: ## Format with ruff
	uv run ruff format src/ loadtest/report.py

lint: ## Lint with ruff
	uv run ruff check src/ loadtest/report.py

clean: ## Remove .venv and __pycache__
	rm -rf .venv src/**/__pycache__ src/__pycache__ .ruff_cache
