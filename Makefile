.PHONY: setup format lint typecheck test check clean

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

clean:
	$(PYTHON) -c "from pathlib import Path; import shutil; [shutil.rmtree(path, ignore_errors=True) for name in ('__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache') for path in Path('.').rglob(name)]"
