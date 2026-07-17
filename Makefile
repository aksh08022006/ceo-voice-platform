.PHONY: setup format lint typecheck test check check-all frontend-setup frontend-check doctor demo benchmark profiles ali-profile matei-profile api frontend-dev clean

PYTHON := .venv/bin/python

setup:
	python3 -m venv .venv
	$(PYTHON) -m pip install -r requirements.lock
	$(PYTHON) -m pip install --no-build-isolation --no-deps -e .

format:
	$(PYTHON) -m ruff check --fix backend/src tests
	$(PYTHON) -m black backend/src tests

lint:
	$(PYTHON) -m ruff check backend/src tests
	$(PYTHON) -m black --check backend/src tests

typecheck:
	$(PYTHON) -m mypy backend/src tests

test:
	$(PYTHON) -m pytest

check: lint typecheck test

frontend-setup:
	cd frontend && npm ci

frontend-check:
	cd frontend && npm run lint && npm run typecheck && npm run build

check-all: check frontend-check

doctor:
	$(PYTHON) -m ceo_voice.profiles.cli doctor

api:
	$(PYTHON) -m uvicorn ceo_voice.api.app:app --host 127.0.0.1 --port 8000 --reload

frontend-dev:
	cd frontend && npm run dev

demo:
	mkdir -p data/demo
	$(PYTHON) -m pytest --no-cov --basetemp=data/demo/latest \
		tests/integration/test_full_workflow.py::test_generated_draft_can_flow_through_human_edit_and_revoice
	@echo "Offline fixture artifacts: data/demo/latest/"

benchmark:
	$(PYTHON) -m pytest --no-cov \
		tests/unit/evaluation/test_engine.py::test_batch_benchmark_and_regression_workflows
	@echo "Fixture reports: data/benchmarks/fixture-report.{json,md}"

ali-profile:
	$(PYTHON) -m ceo_voice.profiles.cli build-development-profile \
		--profile ali-ghodsi \
		--capture data/runtime/incoming/ali-ghodsi-linkedin-screenshot-batch-001.normalized.json \
		--capture data/runtime/incoming/ali-ghodsi-linkedin-screenshot-batch-002.normalized.json \
		--capture data/runtime/incoming/ali-ghodsi-linkedin-screenshot-batch-003.normalized.json \
		--capture data/runtime/incoming/ali-ghodsi-x-screenshot-batch-001.normalized.json \
		--capture data/runtime/incoming/ali-ghodsi-x-screenshot-batch-002.normalized.json \
		--capture data/runtime/incoming/ali-ghodsi-x-screenshot-batch-003.normalized.json \
		--workspace data/runtime/ali/workspace \
		--catalog data/runtime/ali/published/catalog.json

matei-profile:
	$(PYTHON) -m ceo_voice.profiles.cli build-development-profile \
		--profile matei-zaharia \
		--capture data/runtime/incoming/matei-zaharia-linkedin-screenshot-batch-001.normalized.json \
		--capture data/runtime/incoming/matei-zaharia-linkedin-screenshot-batch-002.normalized.json \
		--capture data/runtime/incoming/matei-zaharia-linkedin-screenshot-batch-003.normalized.json \
		--capture data/runtime/incoming/matei-zaharia-linkedin-screenshot-batch-004.normalized.json \
		--capture data/runtime/incoming/matei-zaharia-linkedin-screenshot-batch-005.normalized.json \
		--capture data/runtime/incoming/matei-zaharia-linkedin-screenshot-batch-006.normalized.json \
		--capture data/runtime/incoming/matei-zaharia-x-screenshot-batch-001.normalized.json \
		--capture data/runtime/incoming/matei-zaharia-x-screenshot-batch-002.normalized.json \
		--capture data/runtime/incoming/matei-zaharia-x-screenshot-batch-003.normalized.json \
		--capture data/runtime/incoming/matei-zaharia-x-screenshot-batch-004.normalized.json \
		--workspace data/runtime/matei/workspace \
		--catalog data/runtime/ali/published/catalog.json

profiles: ali-profile matei-profile

clean:
	$(PYTHON) -c "from pathlib import Path; import shutil; [shutil.rmtree(path, ignore_errors=True) for name in ('__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache') for path in Path('.').rglob(name)]"
