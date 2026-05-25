# HANDOFF — codec-comparison-pilot

> Written for the student who will take over this project after I
> (xiangyu.wan) graduate, and extend it to the full JVET CTC.

---

## 1. What you're inheriting

An end-to-end runnable pilot project covering:

- 4 reference encoders (JM-19.1 / HM-18.0 / VTM-23.11 / ECM-18.0)
- 2 test sequences (BasketballDrill Class C + BlowingBubbles Class D)
- 2 configurations (AI + RA)
- 4 QPs (22, 27, 32, 37)

Plus the scaffolding:

- Cross-platform build script (macOS + Linux)
- Python venv (no conda dependency)
- Task scheduler (resumable, concurrent)
- Log parsing, BD-rate computation, report generation
- Pilot baseline verification script

The pilot has already been run on a Mac Studio M4 Max and the baseline
is committed in the git history (search for `Pilot baseline`). Headline
numbers from that run (RA, Y-PSNR):

| Comparison | BasketballDrill | BlowingBubbles |
|---|---|---|
| HM vs JM | −46.4% | −32.4% |
| VTM vs HM | −35.2% | −24.8% |
| ECM vs VTM | −27.8% | −22.1% |
| **ECM vs JM (cumulative, 4 generations)** | **−74.7%** | **−59.9%** |

Time ratios (relative to JM, RA): HM 0.77× (faster, see §7.7), VTM 9.5×,
ECM 99×.

If your reproduction numbers deviate from these by more than ~1%, investigate
the pitfalls in §6 first, then consider environment differences.

---

## 2. First thing: reproduce the pilot

**Do not jump straight to full CTC.** First confirm that your environment
can reproduce the pilot:

```bash
cd codec-comparison-pilot
make venv
source .venv/bin/activate

# Either copy encoder sources into tools/ or point TOOLS_DIR
export TOOLS_DIR=/path/to/encoder/sources

make build
make sanity                     # a few minutes, verifies the build
# Drop YUVs into sequences/ (see sequences/README.md)
make encode                     # pilot: 4-8 h on M4 Max; full CTC: 1–2 weeks
                                # Internally invokes `make subsample-ai` first
make parse bdrate report
make verify-baseline            # critical: must PASS
```

If `verify-baseline` fails, **don't** extend the scope. Investigate:

- Are the encoder versions aligned? (see §3)
- Do the sequence-file MD5s match?
- Have the config files been modified?

Tolerance: `|ΔY-PSNR| < 0.05 dB` and `|Δbitrate|/baseline < 1%`.

---

## 3. Encoder versions — absolutely do not change

| Encoder | Pinned Tag |
|---|---|
| JM  | JM-19.1 |
| HM  | HM-18.0 |
| VTM | VTM-23.11 |
| ECM | ECM-18.0 |

**Any version change invalidates the existing baseline.** If you really have
to upgrade (e.g. a new ECM release):

1. Update the tags in README.md and in the table above.
2. Re-run the pilot scope (`make encode`).
3. Promote the new `raw_metrics.csv` to be the new baseline
   (`make verify-baseline` will auto-stamp when no baseline exists).
4. **Explicitly notify the advisor** of the version change and record it
   in the git commit message.

---

## 4. Extending to full CTC

### 4.1 Class A1 / A2 (4K)

To do:

1. Uncomment `Traffic` and `PeopleOnStreet` in `configs/pilot.yaml`:

   ```yaml
   sequences:
     - BasketballDrill
     - BlowingBubbles
     - Traffic
     - PeopleOnStreet
   ```

2. Download the corresponding YUVs into `sequences/` and update the
   MANIFEST MD5s.

3. Adjust `frames_to_encode`. The pilot uses 64 frames; full CTC should
   use the full sequence length (150 frames for Class A). The
   `total_frames` field in `configs/sequences/Traffic.yaml` is the single
   source of truth.

4. **Memory check**: a 36 GB Mac Studio **cannot run 4K ECM RA in parallel**.
   The Class A portion **must** be moved to a Linux cluster (see §5).
   Alternatively, drop `parallel_jobs` to 1 and run serially (but a single
   ECM 4K RA QP may then take days).

### 4.2 LDB / LDP configurations

Uncomment LDB / LDP in `configs/pilot.yaml`:

```yaml
configs:
  - AI
  - RA
  - LDB
  - LDP
```

The `CONFIG_MAP` in `run_pilot.py` already maps LDB/LDP to each encoder's
corresponding config file — no code changes needed.

### 4.3 Full sequence length

Set `frames_to_encode` in `configs/pilot.yaml` to a value clearly larger
than any sequence length (e.g. 100000), and `run_pilot.py` should clamp
to the `total_frames` from each sequence YAML. **The current implementation
does not yet clamp**; a small change is needed. Specifically:

In `scripts/run_pilot.py`, just before the `build_command()` call, replace:

```python
frames = int(pilot_cfg["frames_to_encode"])
```

with:

```python
frames = min(int(pilot_cfg["frames_to_encode"]), seq["total_frames"])
```

The pilot didn't need this.

### 4.4 Other Classes (B / E / F)

- **Class B (1080p)**: BQTerrace, Cactus, Kimono, ParkScene, BasketballDrive,
  Tango2, FoodMarket4, MarketPlace, RitualDance, CatRobot1, etc. Add a
  `configs/sequences/<Name>.yaml` for each.
- **Class E (720p)**: FourPeople, Johnny, KristenAndSara.
- **Class F (screen content)**: BasketballDrillText, ChinaSpeed, SlideEditing,
  SlideShow. Note that Class F typically requires screen-content-coding
  tools — configurations differ slightly (HM/VTM/ECM each have `_scc.cfg`
  variants which the pilot did not copy; you'll need to copy them manually
  and add entries to `CONFIG_MAP`).

### 4.5 AI subsampling (JVET CTC TSR=8)

The pilot already implements the JVET VVC CTC default for AI: encode every
8th frame (`TemporalSubsampleRatio=8`). Rationale: AI is all-intra, and
adjacent intra frames give near-identical R-D data — JVET itself only
samples for testing. **No change needed for the full CTC extension.**

Implementation details (in case you need to extend or debug):

- VTM/ECM's `encoder_intra_*.cfg` **already have** `TemporalSubsampleRatio=8`.
- HM 18.0's AI cfg defaults to 1, so `run_pilot.py` explicitly passes
  `--TemporalSubsampleRatio=8` on the CLI.
- JM has no such parameter, so `scripts/extract_ai_subsample.py`
  pre-decimates the YUV (writing 1 out of every 8 frames into
  `sequences/<Name>_AI_TSR8.yuv`), which JM reads instead of the source.
- To keep bitrate kbps units consistent (HM/VTM/ECM divide by
  `source_fps/TSR` internally — e.g. 50fps → 6.25Hz), JM is told
  `FrameRate = fps/TSR`.
- `make encode` automatically invokes `make subsample-ai` (idempotent —
  won't regenerate if files exist).

If you (per the advisor's suggestion) want to **drop AI entirely**, change
`configs/pilot.yaml` to:

```yaml
configs:
  - RA
```

All AI-related logic will be skipped automatically.

### 4.6 QP range (important! pilot's range is too narrow)

The pilot uses `qps: [22, 27, 32, 37]`. The resulting BD-rate report had
9 `Insufficient curve overlap` warnings (overlap 47–73%, below the
recommended 75%).

For cross-generation comparisons (especially JM vs ECM), the bitrate
range at the same QP differs so much that a 4-point fit is unstable.
**For full CTC, strongly recommend** expanding to 6 QPs:

```yaml
qps: [17, 22, 27, 32, 37, 42]
```

QP=17 gives JM/HM a low-bitrate anchor; QP=42 gives ECM a high-bitrate
anchor. BD-rate numbers should then track JVET-published values much more
closely (the pilot's ECM-vs-VTM Y came out at −22~−28%, on the high side,
mainly because of insufficient overlap; JVET's published value is around
−10%).

---

## 5. Migrating to a Linux cluster

`scripts/build_all.sh` works as-is on Linux (auto-detects platform, uses
`nproc`).

`scripts/run_pilot.py` uses `concurrent.futures.ProcessPoolExecutor` —
single-node multi-process. On a cluster, two paths:

### 5.1 One big node + raise `parallel_jobs`

If the cluster gives you a 64+ core node, just:

```yaml
# configs/pilot.yaml
parallel_jobs: 32
```

Big and easy.

### 5.2 SLURM job array

Submit one independent SLURM job per `(encoder, sequence, config, qp)`:

```bash
# Skeleton (write your own wrapper)
python scripts/run_pilot.py --dry-run | \
  awk '/^# / && !/jobs/' | \
  while read -r line; do
    JOB_ID=$(echo "$line" | awk '{print $2}')
    sbatch --job-name="$JOB_ID" --output=runs/<run_id>/logs/"$JOB_ID".slurm \
           --wrap="$(echo "$line" | sed 's/^# //')"
  done
```

A more systematic approach would be to write `scripts/run_cluster.py`,
reusing `run_pilot.py`'s `expand_matrix` and command-construction logic,
and translating to SLURM `--array=0-N` submissions. **The pilot did not
implement this.**

A single 4K ECM RA task may run ≥ 24 hours; set `--time` generously
(72:00:00 is safe).

---

## 6. Known pitfalls

### 6.1 Don't use JM's `max_performance` cfg

`tools/JM-JM-19.1/cfg/encoder_max_performance.cfg` is JM's
speed-optimised version with RDOQ and multi-pass disabled — **don't use
it for comparison**. The project uses `cfg/HM-like/encoder_JM_*_HE.cfg`.
See `docs/JM_CTC_alignment.md`.

### 6.2 ECM build failure on ARM macOS

If you hit errors like `error: use of undeclared identifier '_mm_xxx'`
(x86 intrinsics):

1. Check whether that ECM commit temporarily introduced x86-only code.
2. Add `#ifdef __x86_64__` guards around the offending file, save as
   a patch into `tools/patches/ecm_arm_macos.patch`.
3. `build_all.sh` will `git apply` it automatically before configuring.

### 6.3 M4 Max wall-clock times don't extrapolate to Linux servers

When reporting, **use only time ratios** (relative to JM or HM), never
absolute seconds. Absolute numbers are tightly coupled to the machine.

### 6.4 Paths containing spaces

Place the project under a path without spaces. JM's `-p InputFile=…` is
very fragile around shell-escape of spaces.

### 6.5 BD-rate implementation differences

`scripts/compute_bdrate.py` uses the FAU-LMS `bjontegaard` package on PyPI
(note: `bjontegaard`, not the deprecated `bjontegaard_metric`). If you
ever swap in another implementation as a sanity check, results computed
from the same `raw_metrics.csv` should differ by < 0.5%.

### 6.6 HM/VTM/ECM `--Level=` only accepts standard strings

They do not accept trailing-zero formats like `"3.0"` or `"5.0"` — these
fail with:

```
Error parsing option "Level" with argument "3.0".
```

Valid strings: `"1", "2", "2.1", "3", "3.1", "4", "4.1", "5", "5.1", …`.
JM is unaffected — it uses its own Profile/Level IDC parameter
(e.g. 51 = Level 5.1).

The `level` field in every `configs/sequences/*.yaml` has been normalised
to the valid form. **When adding new sequences, be careful**: BlowingBubbles
uses `"3"`, Traffic uses `"5"` — never write `"3.0"`.

### 6.7 VTM/ECM AI cfgs ship with `TemporalSubsampleRatio=8`

Line 61 of both `configs/vtm/encoder_intra_vtm.cfg` and
`configs/ecm/encoder_intra_ecm.cfg` defaults to `TemporalSubsampleRatio: 8`.
This is the JVET VVC CTC default (see §4.5); HM 18 defaults to 1.

**The trap**: if you're not aware of this, the early pilot exhibits the
strange asymmetry "VTM/ECM AI only encoded 8 frames while HM encoded 64"
— HM does 64 frames, VTM/ECM silently subsample to 8, and the BD-rate
ends up comparing different source frames. We hit this during the pilot
and resolved it by aligning all four encoders to TSR=8.

`scripts/run_pilot.py` now forces `TemporalSubsampleRatio=8` for every AI
task: HM/VTM/ECM via `--TemporalSubsampleRatio=8` on the CLI, JM by
reading the pre-decimated `<Name>_AI_TSR8.yuv` file.

### 6.8 Encoder log formats differ (parser handles four dialects)

`scripts/parse_logs.py` maintains regexes for two main log dialects:

| Encoder | Summary block | PSNR line |
|---|---|---|
| JM 19  | `Average data all frames` | `Y { PSNR (dB), cSNR (dB), MSE } : { 41.514, …` |
| HM 18  | `SUMMARY ----------` | `Total Frames \| Bitrate Y-PSNR …` |
| VTM 23 | `LayerId 0` (no `SUMMARY ---` preamble) | same as HM |
| ECM 18 | `LayerId 0` (no `SUMMARY ---` preamble) | same as HM |

VTM/ECM column widths and separators don't exactly match HM — the current
regex uses `\s+` to tolerate the difference. If you upgrade to VTM 24+ or
a newer ECM, run `make parse` first and check for `WARN: could not parse`
lines. If the format changed again, add a fallback to `RE_HM_SUMMARY` in
`parse_logs.py`.

### 6.9 BD-rate "Insufficient curve overlap" warning

The `bjontegaard` package emits this warning for cross-generation
comparisons (9 of them during the pilot):

```
UserWarning: Insufficient curve overlap: '47.40'. Minimum overlap: '75.00'.
```

Meaning: at the 4 chosen QPs, the bitrate ranges of the two encoders
overlap less than 75%. Outside the overlap region, BD-rate is extrapolated
rather than integrated, increasing numerical noise. The pilot chose 4 QPs
for speed; full CTC should expand to 6 QPs (see §4.6).

**This affects only the 2nd decimal place of BD-rate, not the sign or
order of magnitude.** When reporting in the paper, include the overlap
percentage as a note.

---

## 7. Notes for paper writing

If you are taking over toward submission stage:

1. **The methodology section must cite the content of
   `docs/JM_CTC_alignment.md`** (or rewrite it as a paper section).
   The most likely reviewer question is "how did you align JM with CTC?"
2. **Report BD-rate** with Y/U/V channels and 95% confidence intervals
   (averaged across sequences). Also mention the overlap warning from §6.9
   — if you've expanded to 6 QPs per §4.6 this is moot, otherwise be
   honest about it.
3. **Report encoding time** as ratios, never absolute. State the host
   machine (Mac Studio M4 Max, or the cluster model).
4. **The figure "BD-rate gain vs encoding-time multiplier"** is the paper's
   selling point — make sure it's in. The pilot's
   `report/figures/time_scaling.png` is a first draft, but it does not yet
   distinguish RA vs AI markers — upgrade after extending to full CTC.
5. Cite Ohm et al. (IEEE TCSVT 2012) as the methodological baseline; cite
   Bross et al. (Proc. IEEE 2021) as the VVC-section baseline.
6. **The cumulative bar chart is the headline visualisation.** The pilot's
   `report/figures/bdrate_summary.png` compares HM/VTM/ECM all against the
   same JM (AVC) baseline, so the per-generation contribution is directly
   readable. This is the bar chart to include — not the pairwise version.
7. **AI subsampling must be explained.** The pilot uses the JVET CTC default
   TSR=8. If you drop AI entirely, you don't need to mention it. Otherwise
   include something like: "AI BD-rate is computed over frames
   {0, 8, 16, …, 56} per JVET CTC convention, with FrameRate adjusted to
   `source_fps/TSR` for consistent kbps units across all four encoders."
8. **HM is faster than JM** (the pilot's HM RA is ~25% faster than JM)
   — this is **not an algorithmic** speed difference. JM 19.1 has almost
   no SIMD optimisation; HM 18.0 has 10+ years of optimisation. If you
   discuss "algorithmic complexity," note explicitly that
   "all measured times include reference-software optimisation level
   differences." Do not draw the misleading conclusion that "HEVC is
   algorithmically simpler than AVC."
9. **Class D BD-rate is smaller** (the pilot's BlowingBubbles is 10–15
   percentage points lower than BasketballDrill across pairs) — a
   well-known "small-resolution dilutes new-tool benefits" phenomenon.
   Report BD-rate per class (do not average across classes) — JVET does
   the same.

---

## 8. Contact

If you're unsure why I did something a particular way, you can reach me at:
**xiangyu.wan / wanxiangyu82@gmail.com**

Good luck.

— xiangyu.wan, 2026-05 (pilot baseline completed and recorded)
