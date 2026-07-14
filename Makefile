.PHONY: setup format lint typecheck test check doctor demo benchmark clean

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

doctor:
	$(PYTHON) -m ceo_voice.profiles.cli doctor

demo:
	mkdir -p data/demo
	$(PYTHON) -m pytest --no-cov --basetemp=data/demo/latest \
		tests/integration/test_full_workflow.py::test_generated_draft_can_flow_through_human_edit_and_revoice
	@echo "Offline fixture artifacts: data/demo/latest/"

benchmark:
	$(PYTHON) -m pytest --no-cov \
		tests/unit/evaluation/test_engine.py::test_batch_benchmark_and_regression_workflows
	@echo "Fixture reports: data/benchmarks/fixture-report.{json,md}"

clean:
	$(PYTHON) -c "from pathlib import Path; import shutil; [shutil.rmtree(path, ignore_errors=True) for name in ('__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache') for path in Path('.').rglob(name)]"
