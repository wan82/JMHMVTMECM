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

# 4. Provide the input YUVs. Sequence YAMLs store only the bare filename; it is
#    resolved under $YUV_DIR (default: the project's sequences/ dir). Either
#    drop the YUVs into sequences/, or point YUV_DIR at where they already live:
#      export YUV_DIR=/path/to/yuv
#    (keeps machine-specific absolute paths out of the committed configs).

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

> **The head-frames `.bin` is not decodable.** The hook's `exit()` flushes
> stdout/stderr but not the bitstream `ofstream`, so the `.bin` is truncated with
> its tail buffer unwritten. Metrics come from the per-frame log lines, never the
> `.bin` — do not decode it, and do not use its file size to compute bitrate.

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
CTU64 (2040) with headroom. `MAX_CCSAO_CTU_NUM` occurs in only three places —
the constant, the `ccSaoControl[...]` array size, and the `CHECK` — and takes no
part in any bitstream syntax or derivation, so enlarging it **provably cannot
change** results for ≤256-CTU sequences (not just empirically identical). The
array lives only in the ~48-entry `g_ccSaoPrvParam` history (3 components × ≤16
kept params ≈ 184 KB extra), so the memory cost is negligible — though note the
by-value copies of `CcSaoPrvParam` in `VLCReader.cpp` grow ≈840 B → ≈4.7 KB each
(≈5.6×; the struct's other fields sum to ~584 B), worth knowing if anyone ever
profiles CCSAO parsing. CCSAO stays enabled, so ECM's tool set is unchanged.
VTM has no such tool and needs no patch. **Any 4K ECM run requires a one-time
`make build-ecm` after this patch.**

### Known ECM runtime bug: `GeoBlendIntra` assertion (workaround, not a patch)

On certain **QP × content** combinations, ECM aborts *mid-encode* (exit code 1,
after coding some frames) with:

```
ERROR: In function "motionCompensationGeoBlend" in .../InterPrediction.cpp: should be intra and inter
```

It is content/QP-dependent and sporadic — e.g. in the pilot only **RollerCoaster2
QP27** hit it, while QP22/32/37 of the same 4K sequence coded fine.

**Root cause** (verified against ECM-18.0 source). It is *not* that a candidate
is "both intra or both inter" — the candidate builder rejects those inline
(`InterPrediction.cpp:11519–11520`, `"two part are all intra/inter"`). What
actually happens: `GeoBlendInfo::isIntra` default-initialises to `{false,false}`
(`Unit.h:1063`), and the call site (`InterPrediction.cpp:11763–11765`) runs the
`CHECK` on `geoBI.isIntra` **before** it checks the function's return value.
`getGeoBlendIntraCand()` has a `return false` path that leaves `geoBI`
**unwritten** — taken when the RD-chosen merge index `geoMergeIdx0` is out of
range against the candidate count re-derived at motion-compensation time
(`idxCand >= 0 && idxCand < numGeoBlendInfoCand` fails, line 11594). `geoBI` then
stays `{false,false}`, so `!isIntra[0] && !isIntra[1]` is true and the `CHECK`
fires. In short: an **RD-vs-reconstruction desync** (the merge index the encoder
selected can't be reproduced when the candidate list is rebuilt), not an invalid
candidate.

> There is a *second* unwritten-`geoBI` path — the early `return true` at
> `InterPrediction.cpp:11438` when GeoBlend isn't available — currently
> unreachable because both availability checks (`isGeoBlendAvailable` /
> `isGeoBlendIntraAvailable`) are SPS-level constants, so they never flip
> mid-sequence once the tool is on. It would resurface with the **identical**
> error message if GeoBlend availability ever became CU-dependent (e.g. a size or
> mode constraint) — worth knowing before re-debugging this from scratch.

Notes for whoever hits this:

- **A plain retry will not help** — ECM is deterministic (`NumSplitThreads:1`),
  so it re-crashes at the same frame.
- **Do not delete the `CHECK`.** The decoder runs the same derivation
  (`DecCu.cpp:2697`), so an index the encoder picked but can't re-derive is
  unreproducible at decode too — the result is a genuinely **non-decodable**
  bitstream, not merely an encoder-internal inconsistency.
- **Safe workaround: disable the tool for the affected run** via the ECM-only
  passthrough. Where `GeoBlendIntra` is actually set — three levels, a common
  point of confusion:
    - **ECM source built-in default** (`EncAppCfg.cpp:1259`): **0 / off** — only
      the fallback used when no config sets it.
    - **Official ECM RA config** (`encoder_randomaccess_ecm.cfg:156`) **and this
      repo's copy** (`configs/ecm/encoder_randomaccess_ecm.cfg`): **1 / on** —
      unchanged from upstream. So a normal RA run has it **on**.
    - **`--GeoBlendIntra=0`** (passed via `EXTRA=`): a **per-run command-line
      override**, applied only to a specific tool-off re-run; it does **not**
      edit the config file.

  So this repo's RA config is `1` (same as official); `--GeoBlendIntra=0` is a
  one-off runtime override that **deviates** from that config — it genuinely
  disables a tool the CTC config enables (hence the consistency caveat below), it
  is not a harmless "back to default":

  ```bash
  make fastTestTop7 SEQ=RollerCoaster2 EXTRA=--GeoBlendIntra=0
  # general form:
  python scripts/run_pilot.py ... --extra-ecm-args="--GeoBlendIntra=0"
  ```

  `--extra-ecm-args` appends **only** to ECM commands (VTM/HM reject unknown
  options). Use the `--flag=value` form — a value starting with `--` breaks
  argparse otherwise.
- **Consistency caveat.** This makes that point's ECM config differ from the
  tool-on points, but `GeoBlendIntra` is one tool among ~100 (<~0.5% bitrate),
  so for a head-frames diagnostic the effect is negligible. For a rigorous curve,
  re-run *all* QPs of the affected sequence with the flag so the curve is uniform.
- **Debugging tip.** The `printf("getGeoBlendCand( mergeIdx=%d ) failed")` +
  `exit(0)` diagnostic (`InterPrediction.cpp:11781`) sits *after* the `CHECK`, so
  it never prints. To see the offending `mergeIdx`, temporarily move the `CHECK`
  below that block. Beware: it uses `exit(0)` — **exit code 0** — so if you rely
  on it, `run_pilot.py` (which only inspects the return code) would count the
  failed encode as a success; check the log contents, not just the exit status.

### As of the latest release (ECM-20.0), upgrading does **not** fix these

Checked against the current latest ECM version (**20.0**) — both bugs are still
present verbatim in its source:

| Bug | ECM-18.0 | ECM-20.0 |
|---|---|---|
| `MAX_CCSAO_CTU_NUM` (CommonDef.h) | 256 (→ patched to 4096) | **still 256** |
| `ccSaoControl[MAX_CCSAO_CTU_NUM]` fixed array | present | present (identical) |
| `CCSAO CTU out of range` check | present | present (identical) |
| `should be intra and inter` assertion (InterPrediction.cpp) | present | **present, identical** |

So as of 20.0, upgrading buys nothing for these two issues (and would invalidate
the pinned baseline + require re-encoding all ECM points). **Both fixes above
carry forward unchanged** to 20.0; if a future release finally fixes them, drop
the CCSAO patch / `--GeoBlendIntra=0` workaround for that version — but re-check
the source first, since nothing has changed here from 18.0 through 20.0.

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
