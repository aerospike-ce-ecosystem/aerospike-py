IMAGE_REGISTRY := n3r-namespace-mrad1.n3r.reg.navercorp.com/mona-public
IMAGE_NAME := aerospike-benchmark
IMAGE_TAG := latest
IMAGE := $(IMAGE_REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)
K8S_CONTEXT := mrad1-n3r-cluster-admin
K8S_NS := mona-adagent
RUNTIME ?= podman

.PHONY: sync run-benchmark run-asgi-benchmark serve docker-build docker-push deploy undeploy loadtest lint help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

sync: ## Install dependencies
	uv sync

run-benchmark: ## Run pure batch_read benchmark (Rich table + Markdown report)
	PYTHONPATH=src uv run python -m benchmark \
		--clients official official-async py-async \
		--concurrency 10 \
		--batch-sizes 50 200 \
		--iterations 30 \
		--warmup 5 \
		--interleave \
		--shuffle-keys

run-asgi-benchmark: ## Run ASGI serving benchmark (FastAPI + DLRM + Aerospike)
	@echo "Starting FastAPI server in background..."
	PYTHONPATH=src uv run uvicorn serving.app:app --host 0.0.0.0 --port 8000 --workers 1 & \
	SERVER_PID=$$!; \
	echo "Server PID: $$SERVER_PID"; \
	sleep 5; \
	echo "Running ASGI benchmark..."; \
	PYTHONPATH=src uv run python -m serving.asgi_benchmark \
		--base-url http://127.0.0.1:8000 \
		--clients official py-async \
		--iterations 200 \
		--concurrency 10 \
		--warmup 20; \
	echo "Stopping server (PID $$SERVER_PID)..."; \
	kill $$SERVER_PID 2>/dev/null || true; \
	wait $$SERVER_PID 2>/dev/null || true; \
	echo "Done."

serve: ## Run FastAPI serving app locally
	PYTHONPATH=src uv run uvicorn serving.app:app --host 0.0.0.0 --port 8000 --reload

wheel-amd64: ## Cross-compile aerospike-py wheel for linux/amd64 (via zig)
	cd .. && maturin build --release --target x86_64-unknown-linux-gnu --zig \
		-o benchmark/deploy/wheels/ -i python3.11

docker-build: wheel-amd64 ## Build Docker image (pre-built wheel + python deps)
	cd .. && $(RUNTIME) buildx build --platform linux/amd64 \
		-t $(IMAGE) -f benchmark/deploy/Dockerfile .

docker-push: ## Push Docker image to registry
	$(RUNTIME) push $(IMAGE)

deploy: ## Deploy to K8s (mrad1, mona-adagent)
	kubectl --context $(K8S_CONTEXT) apply -k deploy/k8s/ -n $(K8S_NS)
	kubectl --context $(K8S_CONTEXT) -n $(K8S_NS) \
		rollout status deployment/aerospike-benchmark --timeout=180s

undeploy: ## Remove deployment from K8s
	kubectl --context $(K8S_CONTEXT) delete -k deploy/k8s/ -n $(K8S_NS) --ignore-not-found

loadtest: ## Run k6 load test
	k6 run loadtest/k6_benchmark.js

lint: ## Lint Python code
	uv run ruff check src/
	uv run ruff format --check src/
