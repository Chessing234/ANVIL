.PHONY: install init-db seed test test-e2e run api agents lint format clean \
	docker-build docker-up docker-down openapi ci-local

install:
	pip install -e ".[dev]"
	cd frontend && npm install

init-db:
	python scripts/init_db.py

seed:
	python scripts/seed_data.py

test:
	pytest tests/ -v --tb=short --cov=tutorial --cov=api --cov=database --cov=orchestration --cov=config --cov=core --cov=integrations --cov=agents --cov=knowledge --cov=platforms --cov=events --cov=shared --cov-report=term-missing

test-e2e:
	pytest tests/test_e2e/ -v --tb=short

run:
	python main.py --mode full --init-db --seed

api:
	python main.py --mode api

agents:
	python main.py --mode agent

lint:
	ruff check tutorial/ api/ database/ orchestration/ config/ core/ integrations/ agents/ knowledge/ platforms/ events/ shared/ scripts/
	mypy tutorial/

openapi:
	python scripts/export_openapi.py

docker-build:
	docker compose build

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

ci-local: lint
	cd frontend && npm ci && npm run build
	pytest tests/ -v --tb=short
	docker compose build

format:
	ruff format tutorial/ api/ database/ orchestration/ config/ core/ integrations/ agents/ knowledge/ platforms/ events/ shared/ scripts/

clean:
	rm -rf .pytest_cache .mypy_cache *.db frontend/dist
