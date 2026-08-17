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

Ratios are only safe when both sides ran under the **same machine contention**.
A run launched as part of a concurrent batch is slower than the identical run
launched solo, by several percent — enough to invent an effect that isn't there.
See §6.11b for a case where this produced a convincing but entirely fake
"7.8 % speed-up". Record how many jobs were running alongside each measurement.

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

### 6.10 4K ECM must run at `CTUSize 256` — "CCSAO CTU out of range"

**NOTE: if a 4K RA run crashes at startup, first check that ECM's 4K `CTUSize` is
256, not 128** — grep the log banner for `ECM ENC CFG: CTU:`. At CTU128 a
3840×2160 picture is 30×17 = **510** CTUs and overflows CCSAO's fixed
`ccSaoControl[MAX_CCSAO_CTU_NUM=256]` array, aborting at initialisation with
`SampleAdaptiveOffset.cpp:166: CCSAO CTU out of range`. At the CTC's `CTUSize
256` it is only 15×9 = **135** CTUs and fits.

The 256 comes from the per-class CTC cfgs: JVET tunes `CTUSize` and the MTT
depths **per resolution class**, ECM ships them in
`cfg/per-class/class{A,B,C,D}_randomaccess.cfg`, they are mirrored verbatim under
`configs/ecm/per-class/`, and `run_pilot.py` layers the matching file as a
**second `-c`** on every ECM **RA** job (later `-c` wins). VTM never gets these
files (no 256-CTU support, and they contain ECM-only keys).

**AI has no per-class cfg and stays at `CTUSize 128`** — so 4K AI (510 CTUs), and
even 2560×1600 AI (20×13 = 260), still overflow. That is why
`tools/patches/ecm_ccsao_4k.patch` (256 → 4096, auto-applied by `build_all.sh`)
stays applied. It cannot change results — the constant appears only in the array
size and the `CHECK`, never in bitstream syntax — and costs ~184 KB. If AI is
ever dropped from scope (see §4.5), the patch can go with it.

### 6.11 ECM crashes mid-encode on some QP/content: "should be intra and inter"

**The one live ECM blocker.** On certain **QP × content** combinations, ECM
(18.0 and 20.0) aborts *mid-encode* (exit code 1, after coding some frames) with:

```
ERROR: In function "motionCompensationGeoBlend" in .../InterPrediction.cpp:11765: should be intra and inter
```

**The official per-class CTC config (§6.10) does not fix this** — it only moves
which points trip it. Latest head-frames sweep (`TAG=_ctc`), every job with its
class's per-class cfg layered on (the two Class A sequences confirmed at
`ECM ENC CFG: CTU:256`; B/C/D stay at the base `CTU:128` — classC/D carry MTT
overrides only):

| Sequence | Class | QP22 | QP27 | QP32 | QP37 |
|---|---|---|---|---|---|
| RollerCoaster2 | A2 (4K60) | OK | **OK** | OK | OK |
| Campfire | A1 (4K30) | OK | **FAILED** | **FAILED** | OK |
| ParkScene / BQMall / BQSquare | B / C / D | OK | OK | OK | OK |

RollerCoaster2 QP27 — the pilot's only casualty — now passes; **Campfire QP27 and
QP32** fail instead. Expected: changing CTU/MTT changes partitioning → changes the
merge candidate lists → changes *which* points happen to trip it. The defect is
untouched.

> **Both Campfire failures die on the same picture: POC 4 (TId 3), the 5th coded
> picture, right after POC 0/32/16/8** — see
> `runs/fastTop7_Campfire_ctc/logs/000{2,3}_ecm_Campfire_RA_QP{27,32}.log`. QP22
> and QP37 code that same picture fine (all 7 POCs present in their logs). So the
> trigger is a specific block in **Campfire POC 4** that only the mid-QP
> operating points route into the broken path: **content-driven, not
> QP-driven**. Do not assume any QP is safe on an untested sequence. Wall-clock
> to failure was 20.4 h (QP27) and 13.4 h (QP32), i.e. this bug costs most of a
> day per hit on 4K.

Root cause (verified against source, *not* what a first read suggests): it is
**not** that a candidate is both intra or both inter — the builder rejects those
inline (`InterPrediction.cpp:11519–11520`). `GeoBlendInfo::isIntra` defaults to
`{false,false}` (`Unit.h:1063`), and the call site runs the `CHECK` on
`geoBI.isIntra` **before** checking the return value (`InterPrediction.cpp:11763`).
`getGeoBlendIntraCand()` has a `return false` path (line 11594/11600) that leaves
`geoBI` unwritten — taken when the RD-chosen merge index `geoMergeIdx0` is out of
range vs the candidate count re-derived at MC time. `geoBI` stays `{false,false}`
→ the `CHECK` fires. So it's an **RD-vs-reconstruction desync**, and because the
decoder runs the same derivation (`DecCu.cpp:2697`) the stream is genuinely
**non-decodable**. Nothing in that path depends on CTU size — hence §6.10 cannot
help. Nuance: `GeoBlendIntra`'s built-in program default is *off*
(`EncAppCfg.cpp:1259`), but the official upstream RA cfg
(`encoder_randomaccess_ecm.cfg:156`) sets it to 1 — so a standard RA run has it
**on**. `--GeoBlendIntra=0` matches the bare default but *deviates from the
official RA config*: it does disable a CTC-enabled tool (hence the consistency
caveat still applies), it is not a harmless "back to normal ECM".

- A plain retry does **not** help (ECM is deterministic, `NumSplitThreads:1`).
- Do **not** delete the CHECK — the stream would be non-decodable (see above).
- Workaround: disable the tool for the affected run via the ECM-only passthrough:
  `make fastTestTop7 SEQ=Campfire ENC=ecm EXTRA=--GeoBlendIntra=0 TAG=_nogbi`
  (or `run_pilot.py --extra-ecm-args="--GeoBlendIntra=0"`; use the `=` form, VTM
  never receives it). **Two Makefile gotchas**: `fastTestTop7` does *not* forward
  `QP=` (that variable is only wired into the `encode` target), so the command
  above re-runs **all four QPs**, not just the failing one — use `run_pilot.py`
  directly with `--qp` if you want a single point. And always pass `TAG=`, or the
  re-run overwrites `runs/fastTop7_<SEQ>/` in place.
- **The consistency cost of `--GeoBlendIntra=0` is below what this setup can
  measure** — across all five head-frames sequences, BD-rate moves by less than
  ±0.2 % and encoding time by less than the ±5 % timing noise floor. Full
  analysis and the evidence in **§6.11b**. In short: use the flag without
  agonising over it, but for a rigorous curve still re-run *all* QPs of the
  affected sequence so the curve is internally uniform. Cost is strongly QP-dependent: RollerCoaster2 head-7 took 18.0 / 14.8 /
  9.7 / 6.1 h for QP22/27/32/37 (~2.0 days total), Campfire 22.9 / 20.4 / 13.4 /
  10.5 h (~2.8 days) — so budget ~2–3 days per 4K sequence.

### 6.11a Salvaging a crashed QP point: `scripts/estimate_missing_frames.py`

A tool-off re-run gives you the whole curve, but tool-off. This script splices it
with the partial tool-on run so the curve stays usable: **pictures the tool-on
run actually coded are kept as measured**, and only the ones it never reached are
filled from the tool-off donor, corrected by the tool's effect on that same
picture, interpolated in QP from the QPs that did complete.

```bash
python scripts/estimate_missing_frames.py \
  --on-run  runs/fastTop7_Campfire_ctc \
  --off-run runs/fastTop7_Campfire_nogbi \
  --label   Campfire_RA_head7_recon      # --dry-run to print without writing
```

Writes `results/<label>_{frames,summary,validation}.csv`; each picture row is
tagged `measured`/`estimated`, each summary row carries `is_reconstructed`.

**It validates itself — and tells you what the validation misses.** The pictures
a crashed run *did* code (POC 0/32/16/8 at QP27/QP32) are held out, predicted
from the anchors alone, and compared with ground truth. For Campfire the worst
held-out error is **0.353 % bitrate / 0.0049 dB Y-PSNR**. Do not quote that
figure as the accuracy of the reconstruction; three things weaken it, and the
script prints all three:

- **n = 4, not 8.** Half the held-out pictures are I-slices, bit-identical
  between the runs, and prove nothing.
- **The QP37 anchor is uninformative** — the two runs are byte-identical there,
  so the "two-anchor interpolation" is really a scaled single-anchor
  extrapolation from QP22.
- **The held-out pictures are the wrong pictures.** A crash leaves the shallow
  temporal layers (TId 1–2) and takes out the deep ones (TId 3–5) — and TId 3–5
  is precisely what gets filled *and* where the tool's effect is largest. At the
  anchors the tool moves TId 3–5 by up to **0.82 % / 0.019 dB**. **That is the
  number to quote** as the uncertainty on a reconstructed picture.

Also worth knowing: the correction does not beat simply using the donor value
uncorrected (0.385 % / 0.0043 dB), i.e. the tool's effect here is under the
encoder's own RD jitter. A filled-in value is honestly "the tool-off encode of
that picture", not a precise tool-on estimate. The script says so whenever that
holds.

Even at 0.82 % / 0.019 dB the splice stays inside the ±1 % / ±0.05 dB tolerance
of §2 — but that is a *margin*, not a comfort: it means one more crashed
temporal layer, or a sequence where the tool matters more, could push a
reconstruction out of tolerance. Re-run the validation output every time; do not
assume Campfire's numbers transfer.

**Rules for using the output.**

- Estimated points are **never** merged into `results/raw_metrics.csv`. The
  script will not do it and neither should you.
- Any BD-rate, figure, or table built on them must be labelled *reconstructed*,
  stating which pictures were filled and the validated error above.
- `enc_time_sec` is left blank for reconstructed QPs on purpose: a spliced curve
  mixes two tool configurations, so its wall-clock is not a valid complexity
  number (§6.3, §7.3).
- This is a stopgap for the head-frames diagnostic. If Campfire has to appear in
  a **reported** CTC curve, re-run all four QPs uniformly with
  `--GeoBlendIntra=0` and report the curve as tool-off, rather than publishing a
  spliced one.

### 6.11b How big is the GeoBlendIntra effect? Below the noise — and here is the proof

Run it yourself:

```bash
python scripts/analyze_headframes.py \
  --sequences Campfire,RollerCoaster2,ParkScene,BQMall,BQSquare \
  --anchor-recon Campfire=results/Campfire_RA_head7_recon_frames.csv
```

`scripts/analyze_headframes.py` pulls bits / Y-PSNR / ET out of the head-frames
logs, builds one RD point per (sequence, QP), and compares the `_nogbi` runs
against the `_ctc` anchors. The BD-rate itself lives in `scripts/bd_metrics.py`
(PCHIP integral, the JCTVC-L0330 formulation) and reproduces an independent
reference implementation bit-for-bit, so the arithmetic is not in question.

Raw output:

| sequence | BD-rate Y % | time saving % |
|---|---|---|
| Campfire | −0.05 | n/a (reconstructed anchor) |
| RollerCoaster2 | +0.12 | 7.82 |
| ParkScene | +0.04 | 0.91 |
| BQMall | −0.05 | 1.23 |
| BQSquare | −0.18 | 0.44 |

**Do not report these as the tool's effect.** They are dominated by measurement
noise, and the data contains its own proof of that.

**The built-in control.** At **QP37 the `_ctc` and `_nogbi` bitstreams are
bit-identical in all five sequences** — same bits, same PSNR, every picture.
GeoBlendIntra was simply never selected at that operating point, so the two runs
performed identical work. Their encoding times therefore *should* match. They
do not:

| sequence | QP37 apparent time saving |
|---|---|
| ParkScene | +0.03 % |
| BQSquare | +0.26 % |
| BQMall | +0.34 % |
| **RollerCoaster2** | **+4.96 %** |

Identical work, ~5 % apparent difference. **That is the timing noise floor of
this machine, and it swallows every time-saving figure in the table above.** The
script computes and prints this floor automatically, and names the sequences
whose saving falls below it.

**Where RollerCoaster2's 7.82 % came from: CPU contention, not the tool.** The
`_ctc` anchors were launched as a concurrent batch (QP22 overlapped eleven other
encodes), while the `_nogbi` runs had the machine to themselves. The per-QP
"saving" tracks the overlap count almost exactly — 11.26 % (11 concurrent jobs),
7.35 % (3), 3.91 % (1), 4.96 % (1). ParkScene / BQMall / BQSquare had matched
concurrency across both runs and sit at 0.3–2.4 %.

**BD-rate is equally unresolved.** The QP37 points are exact ties in both rate
and quality, so they contribute nothing to the integral — each curve effectively
rests on three points with one endpoint pinned. And the remaining per-QP bitrate
deltas alternate in sign within a sequence (BQSquare: −0.26 / −0.37 / +0.13 /
0.00 %), which is the signature of RD-decision reshuffling rather than a
systematic coding gain.

**The defensible statement:**

> Disabling `GeoBlendIntra` changes coding efficiency by less than ±0.2 % BD-rate
> and changes encoding time by less than the ±5 % timing noise floor of the test
> machine, on all five head-frames sequences. Its true cost is not resolvable
> from this data.

That is enough to justify the workaround in §6.11. It is **not** enough to
publish a number like "saves 2.6 % of encoding time" — that figure is an
artefact of averaging over a contended anchor.

**If a real timing number is ever needed**, re-run with `parallel_jobs: 1`, no
other load on the machine, and the two configurations interleaved rather than
run weeks apart. Expect the true cost to be around 0.2–0.3 % — which is why this
is probably not worth three days of machine time.

**General lesson, applies well beyond this tool.** Encoding times are only
comparable between runs that had the same machine contention. The pilot's own
figures (§1, §7.3) came from a matched batch, so they are fine; but any future
comparison that mixes a batch run with a solo run is measuring the scheduler.
Record concurrency alongside timing, and prefer a bit-identical control point
whenever the experiment offers one — it costs nothing and it is the only thing
that told us the 7.82 % was fake.

### 6.12 As of the latest release (ECM-20.0), upgrading does NOT fix §6.11

Checked against the current latest ECM version (**20.0**): the
`should be intra and inter` assertion and its `getGeoBlendIntraCand` call path
are present verbatim, and `MAX_CCSAO_CTU_NUM` is still 256 (moot at CTU256, see
§6.10). So *as of 20.0* there is **no bug-fix reason to move off the pinned
ECM-18.0** — a version bump would only invalidate the baseline (see §3) and force
re-encoding every ECM point. The workaround and the safety-net patch carry
forward unchanged through 20.0; if some future release finally fixes the
assertion, drop the workaround for that version — but re-check the source first,
since nothing changed from 18.0 through 20.0.

### 6.13 macOS "Killed: 9" on a freshly built encoder (Apple Silicon)

On arm64 macOS, a just-rebuilt encoder binary may be SIGKILLed by AMFI on the
first launch (exit code **-9**, zero output — it dies before `main()`), because
its ad-hoc code signature doesn't validate after `xcodebuild` + `cp` to `bin/`.
The tell: **zero output + exit -9** means the OS killed it pre-launch (a real
crash has output and a different signal). Fix: re-sign in place —
`codesign --force --sign - bin/EncoderApp_ECM && xattr -cr bin/EncoderApp_ECM`.
`build_all.sh` now does this automatically after every copy (`resign_macos`), so
a plain `make build-*` shouldn't hit it again; the manual command is the fallback
if it ever recurs. Distinguish this from §6.10 (that one *does* print the ECM
tool-config banner first, then throws — the program actually ran).

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
