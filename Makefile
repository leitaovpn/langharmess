PYTHON ?= .venv/bin/python

.PHONY: check test install-hooks

check:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m mypy
	$(PYTHON) -m pyright --pythonpath $(PYTHON)
	$(PYTHON) -m pytest tests/test_imports.py -q
	$(PYTHON) -m pytest -q --cov=langharmess_config --cov=langharmess_core --cov=langharmess_plugin --cov=langharmess_api --cov=langharmess_cli --cov-report=term-missing --cov-fail-under=95

test:
	$(PYTHON) -m pytest -q --cov=langharmess_config --cov=langharmess_core --cov=langharmess_plugin --cov=langharmess_api --cov=langharmess_cli --cov-report=term-missing --cov-fail-under=95

install-hooks:
	git config core.hooksPath .githooks
