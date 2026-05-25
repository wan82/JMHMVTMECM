# 01 — Project Structure Walkthrough

> This document walks through every directory and key file in the project so
> that, when you open any file, you know why it lives where it does.
> It complements `README.md`: README is the entry point and quick-start; this
> document is a file-level walkthrough.

---

## 1. Top-level view

```
codec-comparison-pilot/
├── README.md                ← project entry point and quick-start
├── HANDOFF.md               ← post-graduation handoff document
├── Makefile                 ← top-level make targets
├── requirements.txt         ← Python dependencies
├── .gitignore               ← ignore list
├── .venv/                   ← Python virtual env (created by `make venv`)
│
├── configs/                 ← all CTC configs + pilot scope control
├── docs/                    ← project-level technical documentation
├── tutorial/                ← this tutorial series (00–03 + entry README)
├── report/                  ← final report and figures (produced by build_report.py)
├── scripts/                 ← all 8 Python/Shell scripts
├── tools/                   ← encoder source trees (tracked in git; arm-macOS patches travel with the source)
├── sequences/               ← raw YUV files (gitignored; external)
├── bin/                     ← encoder binaries (produced by `make build`)
├── runs/                    ← per-run intermediate artefacts
├── results/                 ← parsed CSVs and baseline
└── logs/                    ← top-level logs (reserved, mostly unused for now)
```

Four groups follow: **entry files**, **configs**, **scripts**, and **outputs**.

---

## 2. Top-level entry files

### 2.1 `README.md`

The first thing anyone sees. Contains:

- Pilot scope summary (2 sequences, 2 configs, 4 QPs)
- Quick-start commands (`make venv` → `make build` → `make encode`)
- Directory layout overview
- Pinned encoder versions table
- Platform-support notes

**Audience:** anyone meeting the project for the first time. After reading
it, they should be able to start running things.

### 2.2 `HANDOFF.md`

The document for the person who takes over after the original author
graduates. Contains:

- How to reproduce the pilot baseline (**first thing to do**)
- The discipline around pinned encoder versions
- How to extend to full CTC (Class A, LDB/LDP, Linux cluster)
- Known pitfalls (ARM macOS build, paths with spaces, BD-rate implementation
  differences)
- Notes for paper writing

**Audience:** the successor, the future project maintainer.

### 2.3 `Makefile`

The project's outward-facing entry point. All concrete logic is delegated
to scripts under `scripts/`; the Makefile itself stays thin. Targets:

| Target | Delegates to | Purpose |
|---|---|---|
| `make help` | (Makefile itself) | List all targets |
| `make venv` | `scripts/setup_env.sh` | Create .venv and install deps |
| `make build` | `scripts/build_all.sh` | Build all four encoders |
| `make build-<encoder>` | same, single encoder | Build just JM/HM/VTM/ECM |
| `make sanity` | `scripts/build_sanity_check.py` | One tiny encode per encoder |
| `make subsample-ai` | `scripts/extract_ai_subsample.py` | Pre-extract every-8th-frame YUVs for JM AI |
| `make encode-dry` | `scripts/run_pilot.py --dry-run` | Print task matrix without executing |
| `make encode` | `scripts/run_pilot.py` | Run the full pilot matrix |
| `make parse` | `scripts/parse_logs.py` | Extract metrics from logs |
| `make bdrate` | `scripts/compute_bdrate.py` | Compute BD-rate |
| `make report` | `scripts/build_report.py` | Generate Markdown report |
| `make verify-baseline` | `scripts/verify_baseline.py` | Verify against the committed baseline |
| `make clean-runs` | (rm) | Clear `runs/` |
| `make clean` | (rm) | Clear .venv, bin, runs, results |

### 2.4 `requirements.txt`

Python dependency list. Pinned minimum versions, not exact pins:

```
numpy>=1.26
pandas>=2.2
scipy>=1.12
matplotlib>=3.8
pyyaml>=6.0
tqdm>=4.66
bjontegaard>=1.3.0
tabulate>=0.9
```

Dependencies are intentionally lightweight — no heavyweight scientific
computing packages. `bjontegaard` (FAU-LMS, on PyPI) is the community-trusted
implementation of BD-rate, used so we don't roll our own.

### 2.5 `.gitignore`

Constrains what does and doesn't enter git. Covers:

- Python artefacts: `.venv/`, `__pycache__/`, `*.pyc`
- Encoder binaries: `bin/` (built locally on each machine)
- Raw videos and encoded output: `sequences/*.yuv`, `*.bin`, `*.264`,
  `*_rec.yuv`, etc.
- Run artefacts: `runs/` (per-timestamp directories that can grow to tens of GB)
- OS junk: `.DS_Store`, `Thumbs.db`

**Kept in git**: scripts, configs, documentation, `results/*.csv` (the pilot
baseline CSV must be tracked), `sequences/MANIFEST.csv` (the sequence
manifest, though the YUVs themselves are not).

---

## 3. `configs/` — the configuration centre

One of the most important directories in the project. Every decision about
"which sequences, which QPs, which configs" is concentrated here.

```
configs/
├── pilot.yaml                  ← scope master control
├── jm/
│   ├── encoder_JM_Intra_HE.cfg   ← JM All-Intra (AI)
│   ├── encoder_JM_RA_B_HE.cfg    ← JM Random Access
│   ├── encoder_JM_LB_HE.cfg      ← JM Low-Delay B
│   └── encoder_JM_LP_HE.cfg      ← JM Low-Delay P
├── hm/
│   ├── encoder_intra_main.cfg
│   ├── encoder_randomaccess_main.cfg
│   ├── encoder_lowdelay_main.cfg
│   └── encoder_lowdelay_P_main.cfg
├── vtm/
│   ├── encoder_intra_vtm.cfg
│   ├── encoder_randomaccess_vtm.cfg
│   ├── encoder_lowdelay_vtm.cfg
│   └── encoder_lowdelay_P_vtm.cfg
├── ecm/
│   ├── encoder_intra_ecm.cfg
│   ├── encoder_randomaccess_ecm.cfg
│   ├── encoder_lowdelay_ecm.cfg
│   └── encoder_lowdelay_P_ecm.cfg
└── sequences/
    ├── BasketballDrill.yaml    ← Class C, enabled in pilot
    ├── BlowingBubbles.yaml     ← Class D, enabled in pilot
    ├── Traffic.yaml            ← Class A1, stub for future expansion
    └── PeopleOnStreet.yaml     ← Class A2, stub for future expansion
```

### 3.1 `configs/pilot.yaml`

The scope-control file. Edit this one file to change the entire pilot scope:

```yaml
encoders:    [jm, hm, vtm, ecm]
configs:     [AI, RA]         # uncomment LDB/LDP to extend
qps:         [22, 27, 32, 37]
sequences:   [BasketballDrill, BlowingBubbles]
frames_to_encode: 64
parallel_jobs: 5
job_timeout_sec: 86400
keep_recon: false
run_dir_pattern: "%Y-%m-%d_%H%M_pilot"
```

`scripts/run_pilot.py` treats this YAML as the single source of truth.

### 3.2 `configs/{jm,hm,vtm,ecm}/`

Four CTC configuration files per encoder (AI / RA / LDB / LDP).

**These files are not hand-written — they are copied verbatim from each
encoder source tree's `cfg/` directory**:

- JM's come from `tools/JM-JM-19.1/cfg/HM-like/` (the JM maintainers' own
  HM-aligned CTC presets)
- HM / VTM / ECM's come from each encoder's official `cfg/` directory

See [02 JM config explained](02_jm_config_explained.md) for details.

### 3.3 `configs/sequences/<name>.yaml`

One YAML per test sequence, recording metadata (no codec-specific
parameters):

```yaml
name: BasketballDrill
class: C
width: 832
height: 480
fps: 50
bit_depth: 8
chroma_format: 420
total_frames: 500
level: "3.1"
yuv_filename: BasketballDrill_832x480_50.yuv
md5: ""                       # filled in after download
source_url: "ftp://..."
```

`run_pilot.py` reads these fields and synthesises the appropriate per-encoder
CLI arguments.

**Why not just use each encoder's own per-sequence cfg files?** Because
they have hard-coded paths, the conventions differ across encoders, and
JM's even ships with Windows-style paths. Using one unified YAML and
translating into each encoder's dialect at runtime is much cleaner.

### 3.4 `configs/sequences/{Traffic,PeopleOnStreet}.yaml`

Stubs for Class A1/A2. **Not used in pilot**, but pre-written so that
extending later only requires uncommenting the corresponding entry in
`pilot.yaml` — no on-the-fly authoring needed.

---

## 4. `scripts/` — all 8 scripts

```
scripts/
├── setup_env.sh                ← (Bash) create venv and install deps
├── build_all.sh                ← (Bash) cross-platform build for all four encoders
├── build_sanity_check.py       ← (Python) one tiny encode per encoder
├── extract_ai_subsample.py     ← (Python) pre-decimate YUVs for JM AI
├── run_pilot.py                ← (Python) task scheduling and execution
├── parse_logs.py               ← (Python) parse logs into a unified CSV
├── compute_bdrate.py           ← (Python) BD-rate computation
├── build_report.py             ← (Python) generate Markdown report + figures
└── verify_baseline.py          ← (Python) regress against the baseline
```

### 4.1 `setup_env.sh`

Idempotent venv initialiser. Logic:

1. Find a Python interpreter (preferring `python3`).
2. Verify version ≥ 3.10.
3. Create the virtual env in `.venv/` (skip if it already exists).
4. Upgrade pip / wheel / setuptools.
5. `pip install -r requirements.txt`.

Safe to rerun — it won't break an existing environment.

### 4.2 `build_all.sh`

The cross-platform build script. The most important Bash script in the
project.

Key design points:

- **Platform auto-detection**: `uname -s` distinguishes Darwin vs Linux,
  and parallelism is determined via `sysctl -n hw.ncpu` (macOS) or `nproc`
  (Linux).
- **External source trees**: defaults to looking under `tools/`; the
  `TOOLS_DIR` env var points to an external directory instead.
- **Glob matching**: `JM-JM-*` / `HM-HM-*` / `VVCSoftware_VTM-VTM-*` /
  `ECM-ECM-*` — minor versions aren't locked.
- **Unified build flow**: each encoder is configured and built with
  `cmake … && cmake --build . --target <ENC>`. On macOS the Xcode generator
  is used; on Linux, Unix Makefiles.
- **ARM macOS compatibility**: auto-applies `tools/patches/<encoder>_arm_macos.patch`
  if present.
- **Subset support**: `./scripts/build_all.sh vtm ecm` builds only VTM and ECM.
- **Unified naming**: artefacts are copied into `bin/` with consistent names:
  `lencod`, `TAppEncoder`, `EncoderApp_VTM`, `EncoderApp_ECM`.

### 4.3 `build_sanity_check.py`

The first quality gate after building. Logic:

- Run AI on the first 16 frames of BlowingBubbles at QP=37 (the cheapest
  workload).
- One full encode per encoder.
- Verify: exit code = 0, and the bitstream file is non-empty.
- On any failure, print the last 10 lines of stderr.

Passing sanity gives you confidence to launch the full 64-task pilot.

### 4.4 `extract_ai_subsample.py`

Pre-decimates source YUVs for JM's AI mode. JM has no native
`TemporalSubsampleRatio`, so to align with VTM/ECM (which use TSR=8 in their
AI configs by default), this script reads every 8th frame from each source
YUV and writes a smaller `<Name>_AI_TSR8.yuv` for JM to read.

Run automatically as a dependency of `make encode`. Idempotent — skips files
that already exist.

See [02 JM config explained](02_jm_config_explained.md) §AI subsampling for
the methodology.

### 4.5 `run_pilot.py`

The task-scheduling core. About 300 lines of Python. Does several things:

1. Read `configs/pilot.yaml` and each sequence YAML.
2. Expand the task matrix: `(encoder × sequence × config × qp)` = 64 Jobs.
3. Synthesise the command line for each Job (JM vs HM/VTM/ECM have very
   different CLI grammars, handled by separate builders).
4. Execute concurrently via `concurrent.futures.ProcessPoolExecutor`.
5. Persist task state to `runs/<timestamp>/jobs.csv`, supporting resume.

Design highlights:

- **CLI abstraction**: `build_cmd_jm` vs `build_cmd_hm_vtm_ecm` hide
  per-encoder syntax differences.
- **Resumability**: each Job updates `jobs.csv` on completion; restart skips
  any job with `status=DONE`.
- **Ordered by expected cost**: JM → HM → VTM → ECM, so cheap tasks fail
  early and expose problems quickly.
- **`--dry-run`**: print all commands but don't execute.
- **`--jobs N`**: override pilot.yaml's `parallel_jobs`.
- **`--run-id`**: resume an existing run directory.

### 4.6 `parse_logs.py`

The log parser. Unifies each encoder's output format into a single CSV.

Key regexes:

- **HM**: finds the `SUMMARY ----` block and extracts frame count, bitrate,
  Y/U/V PSNR, total time.
- **VTM 23 / ECM 18**: same fields, but the SUMMARY block lacks the
  `SUMMARY ----` preamble — instead it's prefixed by `LayerId 0`. The
  parser's regex matches the shared `Total Frames | Bitrate | Y-PSNR | …`
  header line, which is present in both dialects.
- **JM**: looks for `Y { PSNR (dB)`, `U { PSNR (dB)`, `V { PSNR (dB)`,
  `Bit rate`, `Total encoding time` (JM's output is looser, requiring
  several independent regexes).

Output `results/raw_metrics.csv`:

```csv
job_id,encoder,sequence,config,qp,frames_encoded,bitrate_kbps,
psnr_y_db,psnr_u_db,psnr_v_db,enc_time_sec
```

After writing, it does a monotonicity sanity check (QP↑ should always
imply bitrate↓), warning on any violation.

### 4.7 `compute_bdrate.py`

BD-rate computation. For each `(sequence, config)`, computes two views:

Per-generation single-step gains:
- HM vs JM
- VTM vs HM
- ECM vs VTM

Cumulative-vs-AVC gains (used by the primary bar chart):
- HM vs JM (same as above)
- VTM vs JM
- ECM vs JM

Computed separately for Y / U / V channels.

Implementation:

1. Calls the PyPI `bjontegaard` package (community-trusted implementation).
2. Falls back to a built-in piecewise-cubic version if unavailable.

Output `results/bdrate_table.csv` and `results/time_ratio.csv` (encoding
time multipliers).

### 4.8 `build_report.py`

Generates the final Markdown report and PNG figures.

Produces:

- `report/pilot_results.md` — main report (BD-rate table + time-ratio table + figures)
- `report/figures/rd_<sequence>_<config>.png` — one RD curve per `(sequence, config)`
- `report/figures/bdrate_summary.png` — primary BD-rate bar chart, with all
  three test encoders compared against the same JM baseline so the
  per-generation cumulative gain is directly readable
- `report/figures/time_scaling.png` — encoding-time scatter (log scale)

### 4.9 `verify_baseline.py`

The quality guardrail. Logic:

- Compares `results/raw_metrics.csv` (current) against
  `results/pilot_baseline.csv` (baseline).
- Tolerance: `|ΔY-PSNR| < 0.05 dB` and `|Δbitrate|/baseline < 1%`.
- First-time run (no baseline): stamps the current results as the baseline
  automatically.
- On failure: prints every `(encoder, sequence, config, qp)` that exceeded
  the tolerance.

This is the regression test the successor must run when extending. **If a
future ECM upgrade fails this script, the team should stop and investigate**,
not blindly run the full CTC.

---

## 5. `tools/` — encoder source (tracked in git)

```
tools/
├── README.md                       ← explains how source is placed
├── patches/                        ← ARM macOS compatibility patches
├── JM-JM-19.1/
├── HM-HM-18.0/
├── VVCSoftware_VTM-VTM-23.11/
└── ECM-ECM-18.0/
```

**All four encoder source trees are tracked in git.** Reason: this project
has modified `JM-JM-19.1/CMakeLists.txt`, `HM-HM-18.0/CMakeLists.txt`, and
`HM-HM-18.0/source/Lib/TLibCommon/CMakeLists.txt` for ARM macOS compatibility
(gating hard-coded `-msse4.1` flags to x86 only). Those modifications must
travel with the project — we can't rely on a downloader re-applying them.
So the sources, including the modifications, are committed.

`.gitignore` excludes build outputs:

- `tools/*/build/`  ← CMake-generated build directories
- `tools/*/lib/`    ← HM/VTM/ECM compiled static-library directories
  (note: JM's `source/lib/` is genuine source, unaffected by this rule)
- `tools/*/bin/`    ← compiled binaries (covered by the project-root
  `bin/` rule)

`source/`, `cfg/`, `cmake/`, `CMakeLists.txt`, READMEs, etc. are all tracked.

### Size

After committing, the four source trees total ~**170 MB** (ECM is the
biggest at ~130 MB; the others are small). Not unreasonable for git — a
one-time clone covers everyone.

### `tools/patches/`

Reserved for future compatibility patches that, for some reason, can't be
applied directly to source. Currently empty in active use — directly
editing source is more direct; the patch mechanism is kept as a fallback.

### If you need to change source versions

To upgrade to e.g. JM-19.2 / HM-19.0 / VTM-24.x / ECM-19.x:

1. Replace the source tree at `tools/<encoder>-<new-version>/`.
2. Re-apply the ARM compatibility changes (diff the old CMakeLists to
   see exactly what was changed).
3. Update `scripts/build_all.sh`'s glob pattern if the version-number format
   has changed.
4. Update the pinned-version tables in `README.md` and `HANDOFF.md`.
5. Rerun the pilot and verify the baseline diff against the new version.

---

## 6. `sequences/` — raw YUV

```
sequences/
├── README.md           ← download and placement instructions
├── MANIFEST.csv        ← file list + expected MD5
└── *.yuv               ← actual YUV files (gitignored)
```

### `sequences/MANIFEST.csv`

The sequence inventory: filename, resolution, fps, bit depth, total frames,
MD5, source URL. This file **is tracked in git** as the authoritative
declaration of sequence dependencies.

### `sequences/README.md`

Tells the successor where to download the YUVs, how to compute MD5s, and
how to fill them back into `configs/sequences/<name>.yaml`.

### YUV files themselves

Not tracked. They're large (Class C is ~286 MB each, Class A is 1+ GB),
and they come from the JVET archive — each user downloads them.

---

## 7. `docs/` — project-level technical documentation

```
docs/
└── JM_CTC_alignment.md   ← how JM is aligned with CTC (source material for the paper's methodology section)
```

Currently just one file, because JM is the only encoder that needs special
explanation (HM/VTM/ECM all use their own official CTC, with nothing
remarkable to note).

Future docs (e.g. `BDrate_method.md`, `Cluster_migration.md`) would live here.

---

## 8. `tutorial/` — project tutorials

```
tutorial/
├── README.md                       ← tutorial entry point
├── 00_overview.md                  ← project overview
├── 01_project_structure.md         ← this document
├── 02_jm_config_explained.md       ← JM config explained
└── 03_how_to_run.md                ← how to run the pilot
```

Hand-written human-facing tutorials, all tracked in git. They are
maintained alongside the code — new features or new pitfalls should be
backfilled into the relevant tutorial.

---

## 9. `report/` — final output

```
report/
├── pilot_results.md                ← (produced by build_report.py)
└── figures/                        ← (produced by build_report.py)
    ├── rd_<sequence>_<config>.png
    ├── bdrate_summary.png
    └── time_scaling.png
```

Auto-generated by `make report` and overwritten on each run. **Don't edit
these files by hand** — your edits will be lost on the next run. If you
want to annotate or interpret, create `report/notes_<date>.md` alongside.

That said, it is conventional to commit a snapshot of `pilot_results.md`
and the figures, so that readers can see the results without rerunning code.

---

## 10. Runtime artefact directories

### `bin/` — compiled artefacts

```
bin/
├── lencod                 ← JM
├── TAppEncoder            ← HM
├── EncoderApp_VTM         ← VTM
└── EncoderApp_ECM         ← ECM
```

Produced by `make build`. Strictly local — not tracked. A new machine has
to rebuild.

### `runs/` — per-run intermediate artefacts

Each `make encode` creates a timestamped directory:

```
runs/
└── 2026-05-19_1430_pilot/
    ├── jobs.csv              ← task status + commands
    ├── bitstreams/           ← encoded .264 / .bin files
    ├── logs/                 ← one .log per task
    └── tmp_configs/          ← (reserved, unused for now)
```

Not tracked. Can grow to tens of GB. `make clean-runs` clears it all.

### `results/` — parsed final data

```
results/
├── raw_metrics.csv          ← one row per task
├── bdrate_table.csv         ← BD-rate summary
├── time_ratio.csv           ← time-ratio summary
└── pilot_baseline.csv       ← baseline (stamped on first successful run)
```

**Tracked in git.** The pilot baseline is the project's quality guardrail
and must be version-controlled.

### `logs/` — top-level logs (reserved)

Currently unused. Reserved for possible future global logs (`make encode`
launch banners, error roll-ups, etc.).

---

## 11. The whole picture in one diagram

```
         ┌─────────────┐
         │ pilot.yaml  │  ← edit this one file to change scope
         └──────┬──────┘
                │
                ▼
   ┌────────────────────────────────┐
   │  scripts/run_pilot.py          │
   │  (reads all cfg files under    │
   │   configs/)                    │
   └─────────────┬──────────────────┘
                 │ dispatches
                 ▼
         ┌───────────────┐         ┌────────────────┐
         │  bin/lencod   │         │  sequences/    │
         │  bin/TAppEnc  │ ◄─read─ │  *.yuv         │
         │  bin/Enc_VTM  │         │  (gitignored)  │
         │  bin/Enc_ECM  │         └────────────────┘
         └──────┬────────┘
                │ encode
                ▼
   ┌─────────────────────────────────┐
   │  runs/<timestamp>/              │
   │    ├── bitstreams/              │
   │    ├── logs/                    │
   │    └── jobs.csv                 │
   └─────────────┬───────────────────┘
                 │
                 ▼
         ┌───────────────────┐
         │ parse_logs.py     │
         │ compute_bdrate.py │  ──► results/*.csv  (tracked)
         │ build_report.py   │  ──► report/pilot_results.md + figures/
         │ verify_baseline   │
         └───────────────────┘
```

Each arrow corresponds to a Makefile target: `make encode` → `make parse`
→ `make bdrate` → `make report` → `make verify-baseline`.

If you can point to "where I would change the scope," "where every per-run
number ends up," and "how to verify against the baseline" on this diagram,
you've mastered the project's structure.

---

Next: [02 JM config explained](02_jm_config_explained.md) — why JM needs
its own dedicated document.
