# 03 — How to Run

> This document walks through the entire pilot from zero — every step from
> installing dependencies to producing the final report.
> Assume you have just cloned the project (or just received a folder copy
> from your advisor) and have installed nothing yet.

---

## 0. Prerequisites

Minimum machine and software requirements:

| Item | Requirement |
|---|---|
| OS | macOS 14+ (Apple Silicon recommended) or Linux Ubuntu 22.04+ |
| RAM | ≥ 16 GB (36 GB recommended for pilot; more needed for 4K) |
| Disk | ≥ 50 GB free (YUVs dominate) |
| Python | 3.10+ |
| CMake | 3.22+ |
| C++ compiler | clang 14+ or gcc 11+ |
| Git | 2.40+ (used for `git apply` of patches) |

On macOS, Xcode Command Line Tools are enough (`xcode-select --install`) —
the full Xcode app is not required. On Linux, `build-essential` + `cmake` +
`python3-venv` is enough.

---

## 1. Verify the project location

Make sure you are in the right directory:

```bash
cd /path/to/JM_HM_VTM_ECM/codec-comparison-pilot
pwd
# Should print the above path
```

Confirm the four encoder source trees are siblings:

```bash
ls ..
# Should show:
#   ECM-ECM-18.0/
#   HM-HM-18.0/
#   JM-JM-19.1/
#   VVCSoftware_VTM-VTM-23.11/
#   codec-comparison-pilot/    ← you are here
```

---

## 2. Step 1: create the Python virtual env

```bash
make venv
```

This calls `scripts/setup_env.sh`, which does several things:

- Finds `python3` (must be ≥ 3.10)
- Creates `.venv/` in the project root
- Installs all dependencies from `requirements.txt`

Expected time: 1–2 minutes.

Activate after creation:

```bash
source .venv/bin/activate
```

Your shell prompt should now show a `(.venv)` prefix. Verify:

```bash
which python
# Should print .../codec-comparison-pilot/.venv/bin/python
python -c "import pandas, matplotlib, yaml, bjontegaard; print('OK')"
# Should print OK
```

---

## 3. Step 2: build the four encoders

### 3.1 Point to the source location

The four encoder source trees live at `../` (the project's parent
directory). Tell the build script to look there:

```bash
export TOOLS_DIR=$(cd .. && pwd)
echo "TOOLS_DIR=$TOOLS_DIR"
# e.g. /path/to/JM_HM_VTM_ECM
```

> This line has to be re-run in every new shell. If that's annoying, add it
> to your `~/.zshrc` or create a `setup.sh` in the project root to source.

### 3.2 Build

```bash
make build
```

`scripts/build_all.sh` builds JM → HM → VTM → ECM sequentially. Expected
times (Mac Studio M4 Max, parallel build):

| Encoder | Build time |
|---|---|
| JM | ~1 min |
| HM | ~3–5 min |
| VTM | ~5–10 min |
| ECM | ~10–20 min |
| **Total** | **~20–35 min** |

To build a single encoder for a quick try:

```bash
make build-jm    # or build-hm / build-vtm / build-ecm
```

### 3.3 Verify the build

After completion:

```bash
ls -lh bin/
# Should show:
#   lencod              (JM,  ~1 MB)
#   TAppEncoder         (HM,  ~10 MB)
#   EncoderApp_VTM      (~15 MB)
#   EncoderApp_ECM      (~20 MB)
```

Run `--help` on each binary (HM/VTM/ECM) or `-h` (JM) to confirm they start:

```bash
./bin/TAppEncoder --help 2>&1 | head -5
./bin/EncoderApp_VTM --help 2>&1 | head -5
./bin/EncoderApp_ECM --help 2>&1 | head -5
./bin/lencod -h 2>&1 | head -5   # JM uses -h
```

### 3.4 If the build fails

**JM won't build**: rare — JM is pure C and builds almost anywhere. Look at
the error stack; usually it's a missing `#include`. Install
`xcode-select --install` on macOS or `apt install build-essential` on Linux.

**HM won't build**: probably CMake too old (need ≥ 3.22). `brew upgrade cmake`
or `pip install cmake --upgrade`.

**VTM/ECM won't build on ARM macOS**: the most common error is a file using
x86-only intrinsics or inline assembly. Paste the error stack. Quick fix:

```bash
# Find the offending file, add #ifdef __x86_64__ guards
# Then save as a patch
cd $TOOLS_DIR/ECM-ECM-18.0
git diff > /path/to/codec-comparison-pilot/tools/patches/ecm_arm_macos.patch
```

The next `make build-ecm` will auto-apply the patch.

---

## 4. Step 3: prepare the test sequences

### 4.1 Download the YUVs

The pilot needs two sequences:

| Filename | Source | Size |
|---|---|---|
| `BasketballDrill_832x480_50.yuv` | JVET CTC | ~286 MB |
| `BlowingBubbles_416x240_50.yuv` | JVET CTC | ~72 MB |

JVET official FTP (user `hevc`, password `US88Hula`):

```
ftp://hevc:US88Hula@ftp.tnt.uni-hannover.de/testsequences/
```

You can also ask the advisor's lab — most reliable.

Place them in `sequences/`:

```bash
ls sequences/
# BasketballDrill_832x480_50.yuv
# BlowingBubbles_416x240_50.yuv
# MANIFEST.csv
# README.md
```

### 4.2 Verify the MD5

After download, compute the MD5:

```bash
# macOS
md5 sequences/BasketballDrill_832x480_50.yuv
md5 sequences/BlowingBubbles_416x240_50.yuv

# Linux
md5sum sequences/BasketballDrill_832x480_50.yuv
md5sum sequences/BlowingBubbles_416x240_50.yuv
```

Paste the MD5 into the `md5:` field of `configs/sequences/BasketballDrill.yaml`
and `BlowingBubbles.yaml`. Optionally also update `sequences/MANIFEST.csv`.

---

## 5. Step 4: sanity check (do not skip)

```bash
make sanity
```

`scripts/build_sanity_check.py` runs the cheapest possible workload (16
frames of BlowingBubbles AI at QP=37) once per encoder. Expected output:

```
=== Sanity check: JM ===
  OK (3142 bytes)

=== Sanity check: HM ===
  OK (2891 bytes)

=== Sanity check: VTM ===
  OK (2654 bytes)

=== Sanity check: ECM ===
  OK (2401 bytes)

Summary: 4 ok, 0 failed.
```

If **any one fails**, **stop and investigate** before going further. Common
causes:

- Binary missing → go back to Step 2.
- YUV missing → go back to Step 3.
- Encoder config missing → check `configs/{enc}/` is complete.
- ECM timing out after a few minutes → ECM startup is slow, but 16-frame
  AI should still finish in under 5 min; otherwise the binary may be
  broken.

---

## 6. Step 5: dry-run the task matrix

```bash
make encode-dry
```

This prints the **full command lines for all 64 tasks** without executing
them. Check that:

1. **Total tasks = 64** (4 encoders × 2 sequences × 2 configs × 4 QPs).
2. **JM commands contain `-p QPISlice=`, `-p QPPSlice=`, `-p QPBSlice=`,
   all set to the same value.**
3. **HM/VTM/ECM commands contain a single `--QP=`.**
4. **All commands contain `--IntraPeriod=32`** (50-fps sequences).
5. **Paths are absolute** — no Windows-style `D:\…` or relative paths.

Any anomaly indicates a broken config or script.

---

## 7. Step 6: run the pilot

### 7.1 Launch

```bash
make encode
```

Or invoke the script directly (more flexible):

```bash
python scripts/run_pilot.py
```

After launch, you'll see output like:

```
Run directory: runs/2026-05-19_1430_pilot
Pending: 64 / Total: 64 (parallel=5)
[1/64] 0001_jm_BlowingBubbles_AI_QP22 -> DONE (elapsed=2.3s)
[2/64] 0002_jm_BlowingBubbles_AI_QP27 -> DONE (elapsed=1.9s)
...
```

### 7.2 Expected wall-clock (M4 Max, 5 parallel)

| Stage | Cumulative time |
|---|---|
| JM all 16 tasks | < 30 min |
| HM all 16 tasks | ~1 hour |
| VTM all 16 tasks | ~6 hours |
| ECM all 16 tasks | ~few hours |
| **Total (pilot)** | **~4–8 hours** |

ECM is the absolute bottleneck. Recommended: start before going to sleep
and let it run overnight.

### 7.3 What you can do during the run

**Resume**: if it dies (power, kill, machine restart), `make encode` will
auto-skip tasks with status=DONE and continue from where it left off.

**Monitor progress**: open another terminal:

```bash
# Task status counts
awk -F, 'NR>1 {print $6}' runs/$(ls -t runs | head -1)/jobs.csv | sort | uniq -c

# Live tail of the most recent log
tail -f runs/$(ls -t runs | head -1)/logs/$(ls -t runs/$(ls -t runs | head -1)/logs/ | head -1)
```

**Adjust parallelism**: if 5-way parallel runs the machine too hot, drop
to 2 temporarily:

```bash
python scripts/run_pilot.py --jobs 2
```

**Change scope**: edit `configs/pilot.yaml` (e.g. drop ECM to first
validate the other three), save, and rerun. `run_pilot.py` will re-expand
the matrix — **note that this creates a new `runs/<timestamp>/` directory**
without polluting earlier runs.

### 7.4 Determining completion

After completion:

```bash
ls runs/$(ls -t runs | head -1)/
# bitstreams/    ← 64 files
# logs/          ← 64 .log files
# jobs.csv       ← all status=DONE
```

Every row in `jobs.csv` should be `status=DONE` and `exit_code=0`. If any
are `FAILED`:

```bash
# Find the failed ones
awk -F, '$6 == "FAILED"' runs/$(ls -t runs | head -1)/jobs.csv
```

Look at the log for each failure:

```bash
tail -30 runs/$(ls -t runs | head -1)/logs/<failed_job_id>.log
```

If only one or two failed (e.g. one-off disk-full), edit jobs.csv to set
the row's status to `PENDING` (or use a Python one-liner), then rerun
`make encode` to retry.

---

## 8. Step 7: parse, compute BD-rate, generate report

Run in order:

```bash
make parse      # 1s: extract metrics from logs into results/raw_metrics.csv
make bdrate     # 1s: compute BD-rate into results/bdrate_table.csv
make report     # a few seconds: generate Markdown report + PNG figures
```

Or chain them in one command:

```bash
make parse bdrate report
```

### 8.1 Inspect the results

```bash
# Raw per-task metrics (64 rows)
column -t -s, results/raw_metrics.csv | head -10

# BD-rate summary
column -t -s, results/bdrate_table.csv

# Time-ratio summary
column -t -s, results/time_ratio.csv

# Final report
cat report/pilot_results.md

# Figures
open report/figures/   # macOS
# or
xdg-open report/figures/  # Linux
```

### 8.2 Sanity-check your numbers

BD-rate should fall in these ranges (Y channel, RA config):

| Comparison | Expected BD-rate (Y, RA) |
|---|---|
| HM-vs-JM | -35% to -45% |
| VTM-vs-HM | -30% to -40% |
| ECM-vs-VTM | -15% to -25% |
| ECM-vs-JM | -75% to -85% |

If the numbers are off:

- **Too small in magnitude** → is JM accidentally running with the default
  cfg? Check that `configs/jm/encoder_JM_RA_B_HE.cfg` really is the
  HM-like version.
- **Too large in magnitude** → is JM running max_performance cfg? Or is
  IntraPeriod out of alignment?
- **A generation regresses (positive number)** → BUG, immediately
  investigate cfg, IntraPeriod, and QP alignment.

---

## 9. Step 8: lock in the baseline

After your first successful full run with sane numbers:

```bash
make verify-baseline
```

On the first run there is no baseline, so the script copies your current
`results/raw_metrics.csv` to `results/pilot_baseline.csv`.

**Remember to commit the baseline to git**:

```bash
git add results/pilot_baseline.csv results/bdrate_table.csv results/time_ratio.csv
git commit -m "pilot v1 baseline: JM-19.1/HM-18.0/VTM-23.11/ECM-18.0 on Class C+D, 64 frames"
```

Afterwards, any upgrade (encoder version, added sequence, added config)
must rerun and pass `make verify-baseline` (tolerance: 0.05 dB / 1%
bitrate). A failure means a regression was introduced — investigate.

---

## 10. Common cheatsheet

```bash
# Full first-time run
make venv
source .venv/bin/activate
export TOOLS_DIR=$(cd .. && pwd)
make build
# Download YUVs into sequences/
make sanity
make encode-dry           # inspect the matrix
make encode               # actual run (4–8 h on M4 Max)
make parse bdrate report
make verify-baseline      # stamp the baseline

# Routine rerun
source .venv/bin/activate
make encode               # auto-skips DONE tasks
make parse bdrate report

# Debug a single task
python scripts/run_pilot.py --dry-run | grep "jm_BasketballDrill_AI_QP22"
# Paste the command and run by hand

# Wipe and redo
make clean-runs           # only clears runs/
make clean                # clears .venv/bin/runs/results
```

---

## 11. Next steps

After getting the pilot running, recommended reading:

- [HANDOFF.md](../HANDOFF.md) — how to hand the project off before graduation
- [docs/JM_CTC_alignment.md](../docs/JM_CTC_alignment.md) — methodology
  material for the paper
- [02 JM config explained](02_jm_config_explained.md) — if you still have
  questions about JM specifics

If you encounter a problem the tutorials don't cover, please add it to
[HANDOFF.md](../HANDOFF.md) §6 "Known Pitfalls" — the next person will
thank you.
