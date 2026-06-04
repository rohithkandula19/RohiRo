.PHONY: eval eval-verbose api web docker-up docker-down

# always set the right pg URL since the docker compose maps to 5435
export RO_POSTGRES_URL ?= postgresql://ro:ro_local_dev@localhost:5435/ro
export RO_REDIS_URL ?= redis://localhost:6379/0

eval:
	uv run python -m api.eval.harness

eval-verbose:
	uv run python -m api.eval.harness --verbose

eval-actions:
	uv run python -m api.eval.harness --filter actions --verbose

api:
	uv run uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload

web:
	cd web && pnpm dev

docker-up:
	docker compose up -d postgres redis

docker-down:
	docker compose down
