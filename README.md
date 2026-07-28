# codec-comparison-pilot

A pilot project for cross-generation comparison of JM (AVC) / HM (HEVC) /
VTM (VVC) / ECM (post-VVC) on a subset of JVET CTC sequences. The design is
intended to be extended to the full CTC by the team after the pilot phase.

> **License note.** Third-party encoder sources under `tools/` (JM, HM, VTM, ECM)
> are redistributed under their respective licenses — see each
> `tools/<encoder>/COPYRIGHT_ITU.txt`, `COPYRIGHT_ISO_IEC.txt`, and
> `disclaimer.txt` file. The pilot scaffolding (scripts, configs, docs in this
> repo) is original work and may be reused freely for academic purposes.

## Scope (pilot)

- Test sequences: **BasketballDrill** (Class C) + **BlowingBubbles** (Class D)
- Configurations: **AI** (All-Intra) + **RA** (Random Access)
- QPs: 22, 27, 32, 37
- Frames per task: 64 consecutive frames for RA; 8 sub-sampled frames for AI
  (JVET CTC convention with TemporalSubsampleRatio = 8)
- Total: 4 encoders × 2 sequences × 2 configurations × 4 QPs = **64 encodes**
- Target hardware: Mac Studio M4 Max, 36 GB
- Expected wall-clock: 4–8 hours on M4 Max (ECM is the bottleneck)

Class B sequences are intentionally excluded to keep the pilot tractable.
Edit `configs/pilot.yaml` to change scope.

## Quick start

```bash
# 1. Create the Python venv and install deps
make venv
source .venv/bin/activate

# 2. Point to the encoder source trees (one of two ways)
#    (a) Copy sources into tools/ — see tools/README.md
#    (b) Or set the TOOLS_DIR environment variable:
export TOOLS_DIR=/path/to/JM_HM_VTM_ECM   # parent dir holding the four source trees

# 3. Build all four encoders (~10–30 min on M4 Max)
make build

# 4. Drop YUV files into sequences/ — see sequences/README.md
#    (BasketballDrill_832x480_50.yuv, BlowingBubbles_416x240_50.yuv)

# 5. Sanity check (one tiny encode per encoder, ~1 minute total)
make sanity

# 6. Print the task matrix without executing it
make encode-dry

# 7. Run the pilot encode matrix
make encode

# 8. Parse logs, compute BD-rate, build the report
make parse bdrate report
```

## Fast mode: `make encode N` (RA head-frames)

For quick iteration and smoke tests, `make encode N` runs a Random-Access
encode but stops the two expensive VVC-family encoders after the first **N
pictures in coding order**, then exits cleanly:

```bash
make encode 7          # VTM/ECM code only POC 0,32,16,8,4,2,1, then stop
```

For a GOP-32 RA hierarchy, `N=7` yields POC **{0, 32, 16, 8, 4, 2, 1}** — the
intra frame plus exactly one picture per temporal layer (TID 0–5). This
exercises the full GOP depth at a tiny fraction of the cost (ECM alone is ~99×
JM, so capping it at 7 pictures is the whole point).

Division of labour in this mode:

| Encoder  | Behaviour                                                    |
|----------|--------------------------------------------------------------|
| JM, HM   | **Full** RA encode with their own native GOP (they're cheap) |
| VTM, ECM | Stop after the first **N** coded pictures (POC 0,32,16,8,4,2,1) |

How it works: the VTM/ECM `EncGOP.cpp` carries a small early-stop hook (see
`tools/patches/{vtm,ecm}_head_frames.patch`) that reads the env var
`PILOT_MAX_CODED_PICS`; `run_pilot.py` sets it only for the VTM/ECM jobs. The
encoder reads enough input frames for the GOP-32 anchor (POC 32) to exist, then
`exit(0)`s after the N-th coded picture with the per-frame log flushed, so
`make parse` still works (`parse_logs.py` aggregates the per-picture lines when
the truncated log has no SUMMARY block).

Optional overrides (any combination):

```bash
make encode 7 QP=32                                 # single QP instead of 22/27/32/37
make encode 7 SEQ=BasketballDrill YUV=/data/x.yuv   # custom input for a sequence
make encode 7 W=1920 H=1080 FPS=60 BD=10            # custom geometry / bit depth
make encode 7 ENC=vtm,ecm                           # only the two capped encoders
make encode-dry 7                                   # preview commands + env, no run
```

> **Note.** The N pictures are a non-contiguous coding-order *diagonal*, so a
> BD-rate computed from a head-frames run is a diagnostic figure, **not** a
> CTC-comparable number. Use this mode for build/pipeline smoke tests and quick
> VTM↔ECM checks, not for reported results. Requires a one-time rebuild of the
> two encoders to activate the hook: `make build-vtm build-ecm`.

## Encoder source patches (`tools/patches/`)

Functional patches applied to the encoder sources at build time by
`scripts/build_all.sh`. The working-tree sources already carry the changes, so a
plain `make build-vtm build-ecm` is enough; the `.patch` files are kept for
review and for re-applying to a pristine re-checkout.

**`{vtm,ecm}_head_frames.patch`** — the head-frames early-stop hook in
`EncGOP.cpp` (env var `PILOT_MAX_CODED_PICS`) used by `make encode N` and
`make fastTestTop7` (see "Fast mode" above).

**`ecm_ccsao_4k.patch`** — raises `MAX_CCSAO_CTU_NUM` from **256 to 4096** in
ECM's `CommonLib/CommonDef.h`. **Without it, ECM aborts at initialisation on any
4K sequence (Class A1/A2)** — it fails in ~0.1 s, before coding a single frame,
with:

```
ERROR: In function "create" in .../SampleAdaptiveOffset.cpp:166: CCSAO CTU out of range
```

Cause: ECM-18.0's CCSAO "reuse CTU" tool (`JVET_AL0142_CCSAO_REUSE_CTU`) stores
per-CTU control in a fixed-size array `uint8_t ccSaoControl[MAX_CCSAO_CTU_NUM]`,
and the cap was set for ~2K (256 CTUs). A 3840×2160 picture at CTU 128 is
30×17 = **510** CTUs, which overflows it. 4096 covers 4K at CTU128 (510) and even
CTU64 (2040) with headroom; the array lives only in the ~48-entry
`g_ccSaoPrvParam` history (3 components × ≤16 kept params), so the extra memory
is negligible, and CCSAO stays enabled — ECM's tool set is unchanged, and results
for sub-4K sequences (≤256 CTUs) are bit-identical before and after the patch.
VTM has no such tool and needs no patch. **Any 4K ECM run requires a one-time
`make build-ecm` after this patch.**

### Known ECM runtime bug: `GeoBlendIntra` assertion (workaround, not a patch)

On certain **QP × content** combinations, ECM aborts *mid-encode* (exit code 1,
after coding some frames) with:

```
ERROR: In function "motionCompensationGeoBlend" in .../InterPrediction.cpp: should be intra and inter
```

`getGeoBlendIntraCand()` occasionally returns a geometric-partition candidate
whose two parts are both intra or both inter, violating the one-intra-one-inter
invariant the blend mode requires; the following `CHECK` then throws. It is
content/QP-dependent and sporadic — e.g. in the pilot only **RollerCoaster2
QP27** hit it, while QP22/32/37 of the same 4K sequence coded fine.

Notes for whoever hits this:

- **A plain retry will not help** — ECM is deterministic (`NumSplitThreads:1`),
  so it re-crashes at the same frame.
- **Do not delete the `CHECK`** — proceeding with the inconsistent candidate
  produces a corrupt / non-conforming bitstream. The assertion is protecting
  encoder–decoder consistency.
- **Safe workaround: disable the offending tool for the affected run**, via the
  ECM-only passthrough added to `run_pilot.py`:

  ```bash
  make fastTestTop7 SEQ=RollerCoaster2 EXTRA=--GeoBlendIntra=0
  # general form:
  python scripts/run_pilot.py ... --extra-ecm-args="--GeoBlendIntra=0"
  ```

  `--extra-ecm-args` appends **only** to ECM commands (VTM/HM reject unknown
  options). Use the `--flag=value` form — a value starting with `--` breaks
  argparse otherwise.
- **Consistency caveat.** This makes that point's ECM config differ from the
  tool-on points, but `GeoBlendIntra` is one of ~100 ECM tools (<~0.5% bitrate),
  so for a head-frames diagnostic the effect is negligible. For a rigorous curve,
  re-run *all* QPs of the affected sequence with the flag so the curve is uniform.

### Upgrading ECM does **not** fix these

Verified directly against **ECM-20.0** source (both bugs present verbatim):

| Bug | ECM-18.0 | ECM-20.0 |
|---|---|---|
| `MAX_CCSAO_CTU_NUM` (CommonDef.h) | 256 (→ patched to 4096) | **still 256** |
| `ccSaoControl[MAX_CCSAO_CTU_NUM]` fixed array | present | present (identical) |
| `CCSAO CTU out of range` check | present | present (identical) |
| `should be intra and inter` assertion (InterPrediction.cpp) | present | **present, identical** |

So upgrading 18.0 → 20.0 buys nothing for these two issues (and would invalidate
the pinned baseline + require re-encoding all ECM points). **Both fixes above
carry forward unchanged**, so if a future run does move to a newer ECM, re-apply
the CCSAO patch and keep the `--GeoBlendIntra=0` workaround.

## Directory layout

```
codec-comparison-pilot/
├── README.md                ← this file
├── HANDOFF.md               ← team handoff notes
├── Makefile                 ← top-level entry point
├── requirements.txt         ← Python dependencies
├── .venv/                   ← created by `make venv`
│
├── configs/
│   ├── pilot.yaml           ← scope and concurrency settings
│   ├── jm/                  ← JM HM-like CTC configs
│   ├── hm/                  ← HM official CTC configs
│   ├── vtm/                 ← VTM official CTC configs
│   ├── ecm/                 ← ECM official CTC configs
│   └── sequences/           ← per-sequence YAML metadata
│
├── docs/
│   └── JM_CTC_alignment.md  ← how JM is aligned with CTC methodology
│
├── tutorial/                ← project tutorials (00–03 + entry README)
├── scripts/                 ← build / run / parse / BD-rate / report / verify scripts
├── tools/                   ← encoder source trees (tracked; build/ and bin/ are gitignored)
├── sequences/               ← raw YUV files (gitignored; manifest is tracked)
├── bin/                     ← compiled encoder binaries (gitignored)
├── runs/                    ← per-run logs and bitstreams (gitignored)
├── results/                 ← parsed CSVs + baseline (tracked)
└── report/                  ← final report + figures (produced by build_report.py)
```

## Pinned encoder versions

| Encoder | Tag        |
|---------|------------|
| JM      | JM-19.1    |
| HM      | HM-18.0    |
| VTM     | VTM-23.11  |
| ECM     | ECM-18.0   |

Do not upgrade in place — any version change should be treated as a fresh
baseline run.

## Platform support

- **macOS** Apple Silicon (primary target — Mac Studio M4 Max)
- **Linux** (Ubuntu 22.04+) — fully supported; intended for when the team
  migrates to a cluster for the full CTC run

The build script auto-detects the platform and picks an appropriate
parallelism level. ARM-macOS-specific gotchas are documented in
`tools/README.md`.

## How to extend the scope

Edit `configs/pilot.yaml` and uncomment the entries you need:

```yaml
configs:
  - AI
  - RA
  - LDB    # uncomment for full CTC
  - LDP    # uncomment for full CTC

sequences:
  - BasketballDrill
  - BlowingBubbles
  - Traffic         # Class A1 — uncomment for full CTC
  - PeopleOnStreet  # Class A2 — uncomment for full CTC
```

Then rerun `make encode` (a fresh `runs/<timestamp>/` directory will be
created).

## Further reading

- `docs/JM_CTC_alignment.md` — explains how JM is configured to align with
  the HM/VTM/ECM CTC methodology
- `HANDOFF.md` — handoff guide for the team taking over after the pilot
