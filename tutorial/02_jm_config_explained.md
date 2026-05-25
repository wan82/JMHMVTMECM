# 02 — JM Configuration Explained

> Of the four encoders, JM is the **only one that needs a dedicated
> explanation**. HM / VTM / ECM all have JVET-numbered CTC documents to
> follow as-is, but JM is from the AVC era and has **no JVET-numbered CTC
> document** of its own.
>
> This document explains how JM is "aligned" with the others, at what level,
> what the JM maintainers did for us, and what we inject at runtime.
>
> This is also the most likely target for reviewer attack in the paper's
> methodology section — please read it through.

---

## 1. Why JM is a special problem

The JVET CTC (Common Test Conditions) framework was formally established
during the HEVC era (around 2010). Before that, the AVC era used **ad-hoc
comparison setups**: every research group used its own parameters, and
papers were not directly comparable.

For a four-generation horizontal comparison, this creates a problem:

| Encoder | Has a corresponding JVET CTC document? |
|---|---|
| JM (AVC) | **No** — CTC was established after AVC had already "aged out" |
| HM (HEVC) | Yes (JCTVC-L1100 and successors) |
| VTM (VVC) | Yes (JVET-Y2010 and successors) |
| ECM (post-VVC) | Yes (latest JVET meeting outputs) |

**If you naively run JM with `cfg/encoder_main.cfg`, you'll be comparing
"old AVC defaults" against "HEVC/VVC CTC configs"** — an asymmetric setup
that makes JM look much weaker than it should, and artificially inflates
the gains of HEVC/VVC/post-VVC.

## 2. The solution: JM 19.x's bundled HM-like configs

Fortunately, the JM maintainers recognised this. From JM-15.x onward, they
added an `HM-like/` subdirectory under `cfg/` with **configurations specifically
tuned to align with HM CTC**:

```
tools/JM-JM-19.1/cfg/HM-like/
├── encoder_JM_Intra_HE.cfg     ← aligned with HM encoder_intra_main.cfg
├── encoder_JM_RA_B_HE.cfg      ← aligned with HM encoder_randomaccess_main.cfg
├── encoder_JM_LB_HE.cfg        ← aligned with HM encoder_lowdelay_main.cfg (B)
├── encoder_JM_LP_HE.cfg        ← aligned with HM encoder_lowdelay_P_main.cfg
└── per-sequence_JM/
    ├── BasketballDrill.cfg
    ├── BlowingBubbles.cfg
    ├── Traffic.cfg
    └── ...                     ← one-to-one with HM cfg/per-sequence/
```

"HE" = **High Efficiency** — turning on CABAC, High Profile, RDOQ, multi-pass
RD, and all the other high-quality coding tools.

This project's core approach is to **copy those 4 HE configs verbatim into
`configs/jm/`**:

```
configs/jm/
├── encoder_JM_Intra_HE.cfg      ← byte-identical to tools/JM-JM-19.1/cfg/HM-like/…
├── encoder_JM_RA_B_HE.cfg
├── encoder_JM_LB_HE.cfg
└── encoder_JM_LP_HE.cfg
```

You can verify with diff:

```bash
diff configs/jm/encoder_JM_RA_B_HE.cfg \
     tools/JM-JM-19.1/cfg/HM-like/encoder_JM_RA_B_HE.cfg
# Empty output = identical
```

## 3. What HM-like actually changed (vs JM defaults)

Comparing HM-like to JM's default `cfg/encoder_main.cfg`, the key differences
fall into five areas.

### 3.1 GOP structure: HM-5.0-style RA reference-frame management

This is the **most important difference**. HM-like enables a set of flags in
the RA config that bring JM's B-picture reference management in line with the
hierarchical-B topology HM has used since HM 5.0:

```
HM50RefStructure       = 1     # default 0; this is the key switch
CRA                    = 1     # default 0; enable Clean Random Access
BLevel0MoreRef         = 1     # default 0; base-layer B uses more refs (HM-aligned)
BIdenticalList         = 1     # default 0; base-layer B has list 0 = list 1
ReferenceReorder       = 1     # paired with the above; reorder refs by POC
HierarchicalCoding     = 3     # default 0; 3 = explicit GOP
ExplicitHierarchyFormat = "B3r1B1r2b0e3b2e3B5r2b4e3b6e3"
NumberBFrames          = 7     # default 0; 7 = GOP size 8 (incl. 1 anchor)
```

**Without `HM50RefStructure = 1`, the JM and HM GOP structures are simply
not comparable.** This is the most critical contribution from the JM
maintainers.

### 3.2 Profile and entropy: High Profile + CABAC + 8×8 transform

```
ProfileIDC             = 100   # High Profile (FRExt), closest to HEVC Main
SymbolMode             = 1     # CABAC (default might be UVLC)
Transform8x8Mode       = 1     # enable 8×8 integer transform (FRExt tool)
```

AVC High Profile is the tool subset closest to HEVC Main — it supports
8×8 transform, weighted prediction, supervised quantisation, etc. **Do not
use Baseline or Main Profile**, which would handicap JM.

### 3.3 RD optimisation: maximum complexity

```
RDOptimization         = 1     # high-complexity RDO (strongest mode)
UseRDOQuant            = 1     # RDOQ on (matches HM)
RDPictureDecision      = 1     # multi-pass RD decision
SearchMode             = 3     # EPZS motion search (fast and accurate)
EarlySkipEnable        = 1     # early-skip detection (matches HM)
SelectiveIntraEnable   = 1     # selective intra decision
```

This set aligns with HM's "almost everything on" tool state. **Do not switch
to `encoder_max_performance.cfg`** — that's JM's speed-first version with
RDOQ and multi-pass off, and it would make JM appear 1.5–3 dB weaker than
its true capability, making the comparison unfair.

### 3.4 Weighted prediction

```
WeightedPrediction       = 1   # explicit weighted prediction for P
WeightedBiprediction     = 1   # weighted bi-prediction for B
ChromaWeightSupport      = 1
UseWeightedReferenceME   = 1
```

HEVC has weighted prediction on by default. AVC supports it but defaults to
off. HM-like turns it on so JM doesn't get steamrolled by HEVC on
fade/cross-dissolve content.

### 3.5 Lambda weights: keep JM's own retuned values

```
LambdaWeightISlice       = 0.65
LambdaWeightPSlice       = 0.68
LambdaWeightBSlice       = 0.68
LambdaWeightRefBSlice    = 0.68
```

**Important**: these lambda weights are **not equal to** HM's `α · W_k`.
Every generation's lambda has been retuned by its own developers for its
own tool set. JM uses this set; HM uses HM's; **the numbers differ, but
each encoder is run at the local optimum within its own RDO framework**.

This is the same question you asked earlier: "how do we unify the RD-cost?"
To restate the answer:

> **Don't try to unify the lambda formulas across encoders. What gets
> unified is the external test protocol — sequences, QPs, IntraPeriod,
> GOP structure, frame counts — not the RDO cost function inside.**

This is the methodology of Ohm 2012 (IEEE TCSVT) and the design principle
behind JM's HM-like config.

---

## 4. Runtime CLI override: the second layer of "tuning"

The HM-like cfg alone isn't enough — some fields are sequence-specific
(paths, dimensions, frame rate), and others change per run (QP, IntraPeriod).
None of these should be hard-coded in the cfg.

`scripts/run_pilot.py`'s `build_cmd_jm` function injects these at runtime
using JM's `-p key=value` CLI mechanism.

### 4.1 What an actual command looks like

E.g. running BasketballDrill RA at QP=32:

```bash
bin/lencod \
    -d configs/jm/encoder_JM_RA_B_HE.cfg \
    -p InputFile=sequences/BasketballDrill_832x480_50.yuv \
    -p OutputFile=runs/2026-05-19_1430_pilot/bitstreams/0017_jm_BasketballDrill_RA_QP32.264 \
    -p ReconFile= \
    -p SourceWidth=832 \
    -p SourceHeight=480 \
    -p OutputWidth=832 \
    -p OutputHeight=480 \
    -p FrameRate=50 \
    -p FramesToBeEncoded=64 \
    -p FrameSkip=0 \
    -p SourceBitDepthLuma=8 \
    -p SourceBitDepthChroma=8 \
    -p OutputBitDepthLuma=8 \
    -p OutputBitDepthChroma=8 \
    -p QPISlice=32 \
    -p QPPSlice=32 \
    -p QPBSlice=32 \
    -p IntraPeriod=32 \
    -p IDRPeriod=32 \
    > runs/2026-05-19_1430_pilot/logs/0017_jm_BasketballDrill_RA_QP32.log 2>&1
```

### 4.2 Source of each override

| Field | Source | Notes |
|---|---|---|
| `InputFile` | `configs/sequences/BasketballDrill.yaml` + `sequences/` path | The cfg's default is a Windows path `D:\origCfP\...` — must be overridden |
| `OutputFile` | `runs/<timestamp>/bitstreams/<job_id>.264` | Auto-generated; job_id is unique |
| `ReconFile=` | Empty string | **Disables recon YUV** — saves disk; pilot doesn't need it |
| `SourceWidth/Height` | sequence YAML | 832, 480 |
| `OutputWidth/Height` | sequence YAML | **JM requires both pairs** (HM/VTM/ECM only need SourceWidth) |
| `FrameRate` | sequence YAML | 50 fps |
| `FramesToBeEncoded` | `configs/pilot.yaml` | Pilot=64 (1–2 GOPs) |
| `FrameSkip` | Fixed at 0 | CTC starts from frame 0 |
| `SourceBitDepth*` | sequence YAML | All 8 (pilot is all 8-bit) |
| `OutputBitDepth*` | sequence YAML | Same |
| `QPISlice/PSlice/BSlice` | `configs/pilot.yaml`'s `qps` list | **All three set to the same QP** (CTC convention) |
| `IntraPeriod` | `ctc_intra_period(fps)` | 50fps → 32, 60fps → 64 |
| `IDRPeriod` | Same as IntraPeriod | Equal to IntraPeriod in RA |

### 4.3 A few subtleties

**`QPISlice = QPPSlice = QPBSlice`**

JM's default cfg uses `QPISlice=32, QPPSlice=33` — P is intentionally 1 QP
above I. **Do not preserve this cascade.** HM-like's `LambdaWeight*`,
`BRefPicQPOffset`, and the hierarchical-B structure already handle QP
cascading internally — passing one QP from outside is the right approach.
All four encoders (JM/HM/VTM/ECM) follow this convention so that the
comparison stays fair.

**`IntraPeriod` aligned across encoders**

CTC specifies an IntraPeriod per frame rate: 50/30 fps → 32, 60 fps → 64.
`run_pilot.py`'s `ctc_intra_period(fps)` function centralises this mapping.
**All four encoders use the same IntraPeriod value** — this is a hard
constraint for fair comparison.

**Force IntraPeriod=1 for AI**

AI = All Intra = every frame is an I-frame. HM-like's
`encoder_JM_Intra_HE.cfg` defaults to 1, but `run_pilot.py` still
explicitly overrides it to guard against accidentally inheriting the RA
value if cfg files are ever combined.

**`ReconFile=` empty string**

JM by default outputs a reconstructed YUV — for 832×480 × 64 frames, that's
~30 MB. Across 64 tasks, ~2 GB of reconstructed YUVs. The pilot doesn't
need them (PSNR is computed inside the encoder), so turning them off saves
disk and I/O time.

**`OutputWidth/Height` must be set**

HM/VTM/ECM only need SourceWidth/SourceHeight, but JM's `lencod` also
requires OutputWidth/OutputHeight (to support source resize, which we don't
use). Setting only SourceWidth would silently produce 176×144 output —
**a quiet bug trap**.

---

## 5. What we "tuned" — the precise version

You should now see that we didn't modify any JM .cfg file. "Tuning" happens
in two layers:

### Layer 1: choose HM-like rather than the default config

| We chose | We rejected |
|---|---|
| `cfg/HM-like/encoder_JM_RA_B_HE.cfg` | `cfg/encoder_main.cfg` (default) |
| `cfg/HM-like/encoder_JM_Intra_HE.cfg` | `cfg/encoder_baseline.cfg` |
| `cfg/HM-like/encoder_JM_LB_HE.cfg` | `cfg/encoder_max_performance.cfg` (speed-first) |
| `cfg/HM-like/encoder_JM_LP_HE.cfg` | `cfg/encoder_extended.cfg` |

This selection itself is a decision — HM-like is the JM maintainers'
horizontal-comparison-aligned version.

### Layer 2: inject per-run parameters via the CLI at runtime

Override the hard-coded paths, QPs, frame counts, IntraPeriod in HM-like cfg
on each run. All of this logic lives in `scripts/run_pilot.py`'s
`build_cmd_jm` function — about 30 lines of code. **Any change shows up
immediately in `git diff`.**

---

## 6. AI subsampling: a third layer for JM only

JM has no `TemporalSubsampleRatio` option. To follow JVET CTC for AI (which
samples every 8th frame; see §6.7 in HANDOFF.md), we pre-decimate the source
YUV into a 8-frame file `<Name>_AI_TSR8.yuv` containing frames
0, 8, 16, 24, 32, 40, 48, 56 of the original. JM reads this file directly.

To keep the kbps units consistent across all four encoders (HM/VTM/ECM
internally divide by `fps/TSR` after subsampling), JM is told
`FrameRate = source_fps / TSR` (= 6.25 for 50-fps content). `build_cmd_jm`
handles this — see the AI branch.

The pre-decimation script is `scripts/extract_ai_subsample.py`, and it runs
automatically as a dependency of `make encode`.

---

## 7. Verifying that JM is running correctly

After passing sanity check, do a manual dry-run to verify the command is
well-formed:

```bash
make encode-dry | grep -A1 "jm_BasketballDrill_RA_QP32"
```

You should see something like §4.1 above. Check that:

1. `-d` points to `configs/jm/encoder_JM_RA_B_HE.cfg` (not main or baseline).
2. The `-p` list includes `QPISlice/PSlice/BSlice`, all set to 32.
3. `IntraPeriod` is 32 (50fps), not 0 or 16.
4. `ReconFile=` is empty (reconstruction disabled).

Then for actual JM results on BasketballDrill RA QP=32 (64 frames),
you should see roughly:

| Metric | Expected range |
|---|---|
| Bitrate | 800–1500 kbps |
| Y-PSNR | 34–37 dB |
| Relative to HM | HM saves ~35–45% bitrate |

If JM **saves more bits than HM** or has higher Y-PSNR — that's **wrong**,
investigate immediately:

1. Has the JM cfg been replaced or modified?
2. Is JM's `HM50RefStructure = 1`?
3. Is JM's `IntraPeriod` the same as HM's?
4. Is the JM QP value really being passed in?

---

## 8. Extension scenarios

### 8.1 Switching to 10-bit sequences (NebutaFestival, SteamLocomotiveTrain)

Future Class A extension will include 10-bit sequences. Required changes:

- HM/VTM/ECM: switch to `encoder_*_main10.cfg` (HM); VTM/ECM default to
  10-bit profile already.
- JM: in `build_cmd_jm`, add an override based on `seq['bit_depth']`:

```python
if seq['bit_depth'] == 10:
    overrides.append("ProfileIDC=110")    # High 10 Profile
```

`InternalBitDepth=10` is already the default in HM-like cfg, so no change
needed there.

### 8.2 Enabling LDB / LDP

In `configs/pilot.yaml`, uncomment:

```yaml
configs:
  - AI
  - RA
  - LDB
  - LDP
```

`run_pilot.py`'s `CONFIG_MAP` already maps LDB/LDP to `encoder_JM_LB_HE.cfg`
and `encoder_JM_LP_HE.cfg` — **no code changes required**.

### 8.3 Per-CTC-spec IntraPeriod

The current `ctc_intra_period(fps)` only distinguishes two cases
(≥55 fps → 64, otherwise → 32). For future sequences at 24/25 fps, follow
the official CTC table:

| Frame rate | IntraPeriod |
|---|---|
| 24 fps | 32 |
| 25 fps | 32 |
| 30 fps | 32 |
| 50 fps | 32 |
| 60 fps | 64 |
| 100 fps | 96 |

You can extend `ctc_intra_period()` accordingly.

---

## 9. References

- `tools/JM-JM-19.1/CHANGES.TXT` — JM 19.x changelog
- `tools/JM-JM-19.1/cfg/HM-like/` — upstream HM-like config directory
- `docs/JM_CTC_alignment.md` — the in-project methodology document
  (soon to become a paper section)
- Ohm, Sullivan, Schwarz, Tan, Wiegand, *Comparison of the Coding
  Efficiency of Video Coding Standards — Including HEVC*, IEEE TCSVT,
  2012 — the methodological baseline for horizontal comparison
- JCT-VC, *Common Test Conditions and Software Reference Configurations*,
  JCTVC-L1100 — the HM CTC document that HM-like targets

---

Next: [03 How to run](03_how_to_run.md) — running the project from scratch.
