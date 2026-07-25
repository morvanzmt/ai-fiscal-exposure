.PHONY: help setup synthetic real test lint clean

help:
	@echo "setup      install the package with dev extras"
	@echo "synthetic  generate fixtures and run the pipeline end to end"
	@echo "real       run the pipeline against config/config.yaml"
	@echo "test       run the test suite"
	@echo "lint       ruff check"
	@echo "clean      remove generated outputs and caches"

setup:
	uv venv
	uv pip install -e ".[dev,notebook,fetch]"

synthetic:
	python scripts/01_fetch.py --synthetic
	python scripts/02_build_dataset.py --config config/config.synthetic.yaml

real:
	python scripts/02_build_dataset.py --config config/config.yaml

test:
	pytest

lint:
	ruff check src scripts tests

clean:
	rm -rf output/figures/*.png output/figures/*.pdf output/tables/*.csv \
	       output/tables/*.json output/manifest.json
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache
