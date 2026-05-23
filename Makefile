# Top-level Makefile for codec-comparison-pilot.
# Provides a uniform entry point: `make venv`, `make build`, `make encode`, `make report`.
# Each target delegates to scripts/ — the Makefile itself stays thin.

PROJECT_ROOT := $(CURDIR)
PYTHON       := $(PROJECT_ROOT)/.venv/bin/python
PIP          := $(PROJECT_ROOT)/.venv/bin/pip

.PHONY: help venv build build-jm build-hm build-vtm build-ecm \
        subsample-ai sanity encode encode-dry parse bdrate report \
        clean clean-runs verify-baseline

help:
	@echo "Targets:"
	@echo "  make venv             Create .venv and install Python deps"
	@echo "  make build            Build all four encoders (JM, HM, VTM, ECM)"
	@echo "  make build-<encoder>  Build a single encoder"
	@echo "  make sanity           Run a single tiny encode per encoder to verify build"
	@echo "  make subsample-ai     Pre-extract every 8th frame for JM AI (CTC AI methodology)"
	@echo "  make encode-dry       Print the full job matrix without executing"
	@echo "  make encode           Run the full pilot encode matrix"
	@echo "  make parse            Parse logs in latest run to results/raw_metrics.csv"
	@echo "  make bdrate           Compute BD-rate from raw_metrics.csv"
	@echo "  make report           Generate Markdown report and figures"
	@echo "  make verify-baseline  Verify current run matches the pilot baseline"
	@echo "  make clean-runs       Remove runs/ contents (keeps results/)"
	@echo "  make clean            Remove .venv, bin/, runs/, results/"

venv:
	bash scripts/setup_env.sh

build:
	bash scripts/build_all.sh

build-jm:
	bash scripts/build_all.sh jm

build-hm:
	bash scripts/build_all.sh hm

build-vtm:
	bash scripts/build_all.sh vtm

build-ecm:
	bash scripts/build_all.sh ecm

sanity:
	$(PYTHON) scripts/build_sanity_check.py

subsample-ai:
	$(PYTHON) scripts/extract_ai_subsample.py

encode-dry: subsample-ai
	$(PYTHON) scripts/run_pilot.py --dry-run

encode: subsample-ai
	$(PYTHON) scripts/run_pilot.py

parse:
	$(PYTHON) scripts/parse_logs.py

bdrate:
	$(PYTHON) scripts/compute_bdrate.py

report:
	$(PYTHON) scripts/build_report.py

verify-baseline:
	$(PYTHON) scripts/verify_baseline.py

clean-runs:
	rm -rf runs/*

clean:
	rm -rf .venv bin/* runs/* results/*
