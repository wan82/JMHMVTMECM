# Top-level Makefile for codec-comparison-pilot.
# Provides a uniform entry point: `make venv`, `make build`, `make encode`, `make report`.
# Each target delegates to scripts/ — the Makefile itself stays thin.

PROJECT_ROOT := $(CURDIR)
PYTHON       := $(PROJECT_ROOT)/.venv/bin/python
PIP          := $(PROJECT_ROOT)/.venv/bin/pip

.PHONY: help venv build build-jm build-hm build-vtm build-ecm \
        subsample-ai sanity encode encode-dry parse bdrate report \
        clean clean-runs verify-baseline fastTestTop7

# Sequences for the top-7 concurrent fast test (one window per sequence).
FASTTOP7_SEQS := Campfire RollerCoaster2 ParkScene BQMall BQSquare

# Encoder set for fastTestTop7 (default VTM+ECM; override with ENC=ecm to skip
# VTM, e.g. for a tool-off ECM re-run whose VTM points already exist elsewhere).
# A plain assignment avoids the comma-in-$(if) pitfall of "vtm,ecm".
FT7_ENC := vtm,ecm
ifneq ($(ENC),)
  FT7_ENC := $(ENC)
endif
# TAG appends a suffix to the run directory name so a variant run (e.g. a
# GeoBlendIntra-off re-run) is recorded separately from the original:
#   TAG=_nogbi -> runs/fastTop7_<SEQ>_nogbi/   (default empty = runs/fastTop7_<SEQ>/)

# --- `make encode N [QP=.. YUV=.. SEQ=.. W=.. H=.. FPS=.. BD=.. ENC=..]` ------
# `make encode 7` runs an RA encode that caps the expensive VTM/ECM encoders to
# the first 7 pictures in CODING order (POC 0,32,16,8,4,2,1 — the I-frame plus
# one picture per temporal layer); JM/HM still encode in full with their own
# GOP. The bare number is a positional argument captured from MAKECMDGOALS.
# Optional VAR=value overrides: QP (single QP), YUV (input path), SEQ (sequence
# name), W/H (width/height), FPS, BD (bit depth), ENC (encoder subset, e.g.
# vtm,ecm). Plain `make encode` (no number) runs the normal full matrix.
ifneq ($(filter encode encode-dry,$(MAKECMDGOALS)),)
  ENCODE_EXTRA := $(filter-out encode encode-dry subsample-ai,$(MAKECMDGOALS))
  CODED_FRAMES := $(firstword $(ENCODE_EXTRA))
  # Turn the bare positional goal(s) (e.g. `7`) into no-ops so `make encode 7`
  # doesn't fail with "No rule to make target '7'". Only defined when
  # encode/encode-dry is actually a goal, so ordinary typos still error.
  ifneq ($(ENCODE_EXTRA),)
$(ENCODE_EXTRA):
	@:
  endif
endif

# Assemble optional run_pilot.py flags from the positional count + VAR overrides.
PILOT_ARGS  = $(if $(CODED_FRAMES),--coded-frames $(CODED_FRAMES))
PILOT_ARGS += $(if $(QP),--qp $(QP))
PILOT_ARGS += $(if $(SEQ),--seq $(SEQ))
PILOT_ARGS += $(if $(YUV),--input $(YUV))
PILOT_ARGS += $(if $(W),--width $(W))
PILOT_ARGS += $(if $(H),--height $(H))
PILOT_ARGS += $(if $(FPS),--fps $(FPS))
PILOT_ARGS += $(if $(BD),--bit-depth $(BD))
PILOT_ARGS += $(if $(ENC),--encoders $(ENC))
PILOT_ARGS += $(if $(EXTRA),--extra-ecm-args='$(EXTRA)')

help:
	@echo "Targets:"
	@echo "  make venv             Create .venv and install Python deps"
	@echo "  make build            Build all four encoders (JM, HM, VTM, ECM)"
	@echo "  make build-<encoder>  Build a single encoder"
	@echo "  make sanity           Run a single tiny encode per encoder to verify build"
	@echo "  make subsample-ai     Pre-extract every 8th frame for JM AI (CTC AI methodology)"
	@echo "  make encode-dry [N]   Print the job matrix without executing"
	@echo "  make encode           Run the full pilot encode matrix"
	@echo "  make encode N         RA head-frames: cap VTM/ECM to first N coded"
	@echo "                        pictures (e.g. 7 -> POC 0,32,16,8,4,2,1);"
	@echo "                        JM/HM full. Opt: QP= YUV= SEQ= W= H= FPS= BD= ENC="
	@echo "  make fastTestTop7 SEQ=X  Top-7 VTM+ECM for one sequence (per-window,"
	@echo "                        4 QPs serial). No SEQ: background-launch all 5."
	@echo "                        Opt: EXTRA='--GeoBlendIntra=0' ENC=ecm TAG=_nogbi"
	@echo "                        (TAG -> separate runs/fastTop7_<SEQ><TAG>/ dir)"
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
	$(PYTHON) scripts/run_pilot.py --dry-run $(PILOT_ARGS)

encode: subsample-ai
	$(PYTHON) scripts/run_pilot.py $(PILOT_ARGS)

# Top-7 concurrent fast test: VTM+ECM (VTM first), first 7 coded pictures only.
#   make fastTestTop7 SEQ=Campfire   # one sequence per window (open 5 windows)
#   make fastTestTop7                # no SEQ: background-launch all 5 at once
# Per window the 4 QPs (from pilot.yaml) run SERIALLY (--jobs 1) so a 4K window
# never holds two encodes at once; each sequence writes its own runs/fastTop7_<SEQ>/.
fastTestTop7:
ifeq ($(strip $(SEQ)),)
	@echo "fastTestTop7: launching VTM+ECM top-7 for 5 sequences concurrently..."
	@mkdir -p runs
	@for s in $(FASTTOP7_SEQS); do \
	  echo "  -> $$s  (log: runs/fastTop7_$${s}$(TAG).out)"; \
	  $(PYTHON) scripts/run_pilot.py --coded-frames 7 --seq $$s \
	    --encoders $(FT7_ENC) --jobs 1 --run-name fastTop7_$${s}$(TAG) \
	    $(if $(EXTRA),--extra-ecm-args='$(EXTRA)') \
	    > runs/fastTop7_$${s}$(TAG).out 2>&1 & \
	done; \
	wait; \
	echo "fastTestTop7: all 5 sequences finished."
else
	$(PYTHON) scripts/run_pilot.py --coded-frames 7 --seq $(SEQ) \
	  --encoders $(FT7_ENC) --jobs 1 --run-name fastTop7_$(SEQ)$(TAG) \
	  $(if $(EXTRA),--extra-ecm-args='$(EXTRA)')
endif

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
