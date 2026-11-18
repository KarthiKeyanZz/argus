# ARGUS developer commands. Run from the argus/ directory.
SHELL := /bin/bash
UV ?= $(shell command -v uv || echo $(HOME)/.local/bin/uv)
COMPOSE ?= podman compose
BACKEND := backend
RUN := cd $(BACKEND) && $(UV) run

CHAT_MODEL  ?= gemma4:26b-a4b-it-qat
EMBED_MODEL ?= nomic-embed-text

.DEFAULT_GOAL := help
.PHONY: help env install db-up db-down db-logs db-psql migrate migrate-status \
        api worker test test-llm lint fmt typecheck check \
        web web-install web-api web-check check-all \
        llm-status llm-pull llm-create llm-gpu

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ------------------------------------------------------------------ setup
env: ## Create .env with a random DB password (only if missing)
	@if [ -f .env ]; then echo ".env already exists - leaving it alone"; else \
	  pw=$$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))'); \
	  sed -e "s/change-me/$$pw/g" .env.example > .env && chmod 600 .env && echo "created .env"; fi

install: ## Install backend dependencies (uv)
	cd $(BACKEND) && $(UV) sync

# ------------------------------------------------------------------ database
db-up: ## Start PostgreSQL (pgvector) container and wait until healthy
	$(COMPOSE) up -d postgres
	@for i in $$(seq 1 40); do \
	  s=$$(podman inspect -f '{{.State.Health.Status}}' argus-postgres-1 2>/dev/null); \
	  [ "$$s" = healthy ] && echo "postgres is healthy" && exit 0; sleep 1; done; \
	  echo "postgres did not become healthy"; exit 1

db-down: ## Stop the database container (data is kept in the volume)
	$(COMPOSE) down

db-logs: ## Tail database logs
	$(COMPOSE) logs -f postgres

db-psql: ## Open psql inside the container
	$(COMPOSE) exec postgres sh -c 'psql -U $$POSTGRES_USER -d $$POSTGRES_DB'

migrate: ## Apply pending SQL migrations
	$(RUN) argus-migrate up

migrate-status: ## Show applied / pending migrations
	$(RUN) argus-migrate status

# ------------------------------------------------------------------ run
api: ## Run the API with auto-reload (Swagger: http://127.0.0.1:8000/docs)
	$(RUN) uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log

worker: ## Run the background worker
	$(RUN) argus-worker

# ------------------------------------------------------------------ quality
test: ## Run tests (needs db-up; LLM tests excluded)
	$(RUN) pytest

test-llm: ## Run tests against the real local model (slow)
	$(RUN) pytest -m llm -v

lint: ## Lint
	$(RUN) ruff check app tests

fmt: ## Auto-format and fix imports
	$(RUN) ruff format app tests && $(RUN) ruff check --fix app tests

typecheck: ## Static type check
	$(RUN) mypy app

check: lint typecheck test ## Everything CI would run

# ------------------------------------------------------------------ frontend
web-install: ## Install frontend dependencies (exact lockfile)
	cd frontend && npm ci

web: ## Run the React UI with hot reload -> http://127.0.0.1:5173 (needs `make api`)
	cd frontend && npm run dev

web-api: ## Regenerate TypeScript API types from the running API's OpenAPI schema
	cd frontend && npm run gen:api

web-check: ## Frontend type check + lint + tests + production build
	cd frontend && npm run typecheck && npm run lint && npm test && npx vite build

check-all: check web-check ## Backend + frontend quality gates

# ------------------------------------------------------------------ LLM
llm-status: ## Ollama version, installed and loaded models, GPU memory
	@ollama --version; echo; ollama list; echo; ollama ps; echo; \
	  nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv

llm-pull: ## Download the chat + embedding models
	ollama pull $(CHAT_MODEL)
	ollama pull $(EMBED_MODEL)

llm-create: ## Build the tuned 'argus-extractor' model from llm/Modelfile.extractor
	ollama create argus-extractor -f llm/Modelfile.extractor

llm-gpu: ## Watch GPU memory while a model runs (Ctrl+C to stop)
	watch -n1 nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv
