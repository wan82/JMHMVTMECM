# JM CTC Alignment

> **Purpose**: explain how the JM (H.264/AVC) reference software is
> configured for a JVET-CTC-compatible operating mode in this project,
> so that horizontal BD-rate comparisons against HM / VTM / ECM are
> meaningful.
>
> **Bottom line**: JM 19.1 already ships, under `cfg/HM-like/`, a set of
> configurations explicitly aligned with HM-style CTC. **No need to write
> JM CTC configs from scratch.** This document explains where those configs
> came from, why they're configured the way they are, and how they should
> be used and extended in the full-CTC workflow.

---

## 1. Background: why JM has no "official CTC"

H.264/AVC was finalised in 2003, but JVET (originally JCT-VC) did not
formally introduce a Common Test Conditions document until the HEVC era
(circa 2010+ — JCTVC-L1100 and successors). JM 19.x is the legacy AVC
reference implementation; **no JVET-numbered CTC document is bound to it**.

But the JM maintainers were aware of the cross-generation comparison need
and **gradually added an HM-aligned config set under `cfg/HM-like/`** from
JM-15.x onward. The JM 19.1 we use already includes the complete set:

```
cfg/HM-like/
├── encoder_JM_Intra_HE.cfg     # corresponds to HM encoder_intra_main.cfg
├── encoder_JM_RA_B_HE.cfg      # corresponds to HM encoder_randomaccess_main.cfg
├── encoder_JM_LB_HE.cfg        # corresponds to HM encoder_lowdelay_main.cfg (B)
├── encoder_JM_LP_HE.cfg        # corresponds to HM encoder_lowdelay_P_main.cfg
└── per-sequence_JM/            # one-to-one with HM cfg/per-sequence/
```

"HE" = High Efficiency — enabling RDO, CABAC, High Profile, and other
high-efficiency tools, corresponding to HM Main profile. **This project uses
that set directly**, copying them into `configs/jm/` as the authoritative
JM configs.

---

## 2. What the HM-like configs align

Aligning against the relevant HM-CTC dimensions, the JM HM-like configs do
the following.

### 2.1 Profile and Level

| Dimension | HM CTC (Main) | JM HM-like (HE) | Notes |
|---|---|---|---|
| Profile | Main (HEVC) | High Profile (`ProfileIDC = 100`) | AVC's High Profile is the tool subset closest to HEVC Main |
| Entropy | CABAC | CABAC (`SymbolMode = 1`) | UVLC is obsolete |
| Transform | 4×4 / 8×8 (HEVC has multi-size TUs) | `Transform8x8Mode = 1` | Enables 8×8 integer transform (FRExt) |
| Bit depth | 8 (or 10) | 8 (`SourceBitDepthLuma = 8`) | Internal 10-bit is on by default (`InternalBitDepth = 10`) |

### 2.2 GOP structure

#### All Intra (AI)

| | HM `encoder_intra_main.cfg` | JM `encoder_JM_Intra_HE.cfg` |
|---|---|---|
| IntraPeriod | 1 (every frame is I) | `IntraPeriod = 1`, `IDRPeriod = 1` |
| Hierarchy | N/A | `HierarchicalCoding = 0` |
| NumberBFrames | 0 | 0 |

→ Fully aligned. AI is "every frame I" in both standards.

#### Random Access (RA)

| | HM `encoder_randomaccess_main.cfg` | JM `encoder_JM_RA_B_HE.cfg` |
|---|---|---|
| GOP size | 16 (hierarchical B) | `NumberBFrames = 7` (i.e. GOP=8 hierarchical B; HM-like template default — full CTC will adjust by resolution) |
| Hierarchy | 4-layer hierarchical-B | `HierarchicalCoding = 3` (explicit GOP) + `ExplicitHierarchyFormat = "B3r1B1r2b0e3b2e3B5r2b4e3b6e3"` |
| Random access | CRA + open GOP | `CRA = 1`, `HM50RefStructure = 1` |
| Reference management | HM 5.0-style RPS | `BLevel0MoreRef = 1`, `BIdenticalList = 1`, `ReferenceReorder = 1` |
| IntraPeriod | per sequence (see §3) | `IntraPeriod = 0` default (overridden per sequence) |

→ The key leap: JM HM-like **explicitly enables the HM-5.0-era reference
management mode via `HM50RefStructure = 1`**, structurally aligning JM's
B-picture referencing with HM RA. This is the single most important
switch in the config.

#### Low-Delay B (LB) / Low-Delay P (LP)

| | HM lowdelay | JM `encoder_JM_LB_HE.cfg` / `LP_HE.cfg` |
|---|---|---|
| LowDelay | yes | `LowDelay = 1` |
| GOP length | 4 (hierarchical B with reference cascade) | `NumberBFrames = 3`, `HierarchicalCoding = 3` + explicit GOP |
| IntraPeriod | 1 second (≈ fps frames) | `IntraPeriod = 0` default (overridden per sequence) |
| LDRefSetting | JCTVC-F701 style | `LDRefSetting = 1` |
| P-only? | LP replaces B with P | LP uses `PReplaceBSlice = 1` |

### 2.3 RD-cost / Lambda

Every HM-like JM config has:

```
LambdaWeightISlice    = 0.65
LambdaWeightPSlice    = 0.68
LambdaWeightBSlice    = 0.68
LambdaWeightRefBSlice = 0.68
```

The lambda formula:

```
λ = LambdaWeight_X · 2^((QP - 12) / 3)
```

This matches HM's lambda formula in form (HM uses `α · W_k · 2^((QP-12)/3)`,
where `α` and `W_k` depend on slice type and temporal layer). **The numbers
cannot match exactly** — each one was retuned for its own tool set — but
the units, formal shape, and dependence on QP are aligned.

> **This is the answer to your earlier question, "how do we unify the
> RD-cost?"** JM HM-like does *not* change lambda to match HM's; it keeps
> JM's own retuned lambda (the local optimum for JM's RDO framework) while
> aligning the external test conditions. This is exactly the methodology
> recommended by Ohm 2012. Details in §5.

### 2.4 High-complexity RDO mode

```
RDOptimization        = 1   # RD-on (high complexity)
SearchMode            = 3   # EPZS
SearchRange           = 64  # CTC default value (HE configs use 128 to match HM on 1080p+)
UseRDOQuant           = 1   # RDOQ on
EarlySkipEnable       = 1   # equivalent to HM fast-skip
RDPictureDecision     = 1   # multi-pass RD decision
```

→ In HE mode, JM enables all the high-quality coding tools. This is a
prerequisite for a fair comparison against HM Main configuration.
**Do not switch to max-performance mode** (`encoder_max_performance.cfg`)
— that would handicap JM unfairly.

### 2.5 Weighted Prediction

```
WeightedPrediction    = 1   # explicit
WeightedBiprediction  = 1   # explicit
```

HEVC has weighted prediction by default. The HM-like JM configs enable it
too, so that JM is not handicapped on fade/cross-dissolve content for
lack of an enabled tool.

---

## 3. Using the JM HM-like configs in full CTC

### 3.1 CLI invocation conventions

JM's CLI **differs in syntax** from HM/VTM/ECM and must be handled
separately.

#### HM/VTM/ECM style

```bash
TAppEncoder \
    -c configs/hm/encoder_randomaccess_main.cfg \
    -c configs/sequences/BasketballDrill.cfg \
    --InputFile=sequences/BasketballDrill_832x480_50.yuv \
    --BitstreamFile=runs/.../bs.bin \
    --ReconFile=/dev/null \
    -q 32 \
    --FramesToBeEncoded=64 \
    --IntraPeriod=32 \
    --SEIDecodedPictureHash=1 \
    > runs/.../log.txt 2>&1
```

Multiple `-c` files stack; CLI overrides use `--Key=Value`.

#### JM style

```bash
lencod \
    -d configs/jm/encoder_JM_RA_B_HE.cfg \
    -f configs/sequences/BasketballDrill_JM.cfg \
    -p InputFile="sequences/BasketballDrill_832x480_50.yuv" \
    -p OutputFile="runs/.../bs.264" \
    -p ReconFile="/dev/null" \
    -p QPISlice=32 -p QPPSlice=32 -p QPBSlice=32 \
    -p FramesToBeEncoded=64 \
    -p IntraPeriod=32 -p IDRPeriod=32 \
    > runs/.../log.txt 2>&1
```

JM uses `-d` for the main config ("default config"), `-f` for a secondary
config to merge, and `-p KEY=VALUE` for overrides. Note that **`-p` must
be immediately followed by the key-value pair with no space**.

This project's `scripts/run_pilot.py` hides these CLI differences and
exposes a single unified task interface for all four encoders.

### 3.2 IntraPeriod per CTC recommendation

CTC specifies IntraPeriod per `(resolution, frame rate)` combination:

| Frame rate | IntraPeriod |
|---|---|
| 24 fps | 32 |
| 30 / 50 fps | 32 |
| 60 fps | 64 |

For the pilot's two sequences (BasketballDrill @ 50 fps,
BlowingBubbles @ 50 fps), CTC recommends IntraPeriod = 32.
`run_pilot.py` reads `fps` from each sequence YAML and computes
automatically. **All four encoders use the same IntraPeriod** — a hard
constraint for fair comparison.

### 3.3 QP list

CTC standard: `QP ∈ {22, 27, 32, 37}`.

- HM/VTM/ECM: a single `-q 32` is enough — the encoder internally cascades
  QP by slice type and hierarchy level.
- JM HM-like: requires setting `QPISlice`, `QPPSlice`, and `QPBSlice`
  **all to the same value**; the `LambdaWeight*` and `BRefPicQPOffset`
  in the HM-like config handle the subsequent cascade.

`run_pilot.py` follows this convention when generating commands.

### 3.4 Frame count and FrameSkip

`FramesToBeEncoded` is fixed at 64 in the pilot (covering 1 AI GOP and
2 RA GOPs). For full CTC, this should be the full sequence length (per
the sequence YAML's `total_frames`).

JM HM-like defaults to `FrameSkip = 0`, and CTC also starts from frame 0.
**Don't change this.**

### 3.5 Per-sequence configurations

JM 19.1 already provides JM-style per-sequence configs for every JVET
CTC sequence under `cfg/HM-like/per-sequence_JM/` (including BasketballDrill,
BlowingBubbles, and future-extension sequences like Traffic, PeopleOnStreet).

However, these files use Windows-style paths (`InputFile = "../../origCfP/..."`),
so this project **does not use them directly**. Instead, `run_pilot.py`
synthesises a temporary JM per-sequence cfg at runtime from
`configs/sequences/<Name>.yaml`. Advantages:

- Cross-platform paths (macOS / Linux)
- `FramesToBeEncoded`, QP, IntraPeriod, etc. controlled centrally from `pilot.yaml`
- Doesn't pollute the upstream configs

---

## 4. Profile selection trade-offs

HM CTC Main profile is 8-bit. VVC Main 10 profile is 10-bit. The
"reference point" bit depth therefore differs across standards. In the pilot:

| Encoder | Input | Internal | Output |
|---|---|---|---|
| JM (High@8) | 8-bit | 8-bit | 8-bit |
| HM Main | 8-bit | 8-bit | 8-bit |
| VTM Main 10 | 8-bit → up-converted to 10 | 10-bit | 10-bit |
| ECM | same as VTM | 10-bit | 10-bit |

**This is the CTC default; the project does not deviate.** PSNR is computed
in the reconstructed YUV domain (HM/VTM/ECM logs already provide the
PSNR corresponding to 8-bit input, directly comparable to JM's PSNR).

If 10-bit comparison becomes relevant in the future (Class A sequences
NebutaFestival and SteamLocomotiveTrain are natively 10-bit), all four
encoders need to be switched to 10-bit profiles — see §6.

---

## 5. RD-cost "unification" — clearing up a common misunderstanding

> **A common misunderstanding**: that fair horizontal comparison requires
> unifying the lambda formulas of JM, HM, VTM, and ECM.
>
> **The correct approach**: keep each encoder's lambda (each generation's
> lambda has been retuned for its own tool set, hitting the local optimum),
> but **unify externally**: same sequence, same IntraPeriod, same QP set,
> same frame count, equivalent GOP structure. Compare BD-rate (fit RD
> curves across multiple QPs), not single points.

JM HM-like does **not** force `LambdaWeight*` to match HM's numbers. What
it does is structural alignment (GOP, reference management, profile, tool
set), **so that JM runs at its own retuned RDO operating point but under
external test conditions identical to HM's**. This is the methodology
used in Ohm 2012 (IEEE TCSVT).

**Important disciplines**:

- Don't change the `LambdaWeight*` fields in `configs/jm/encoder_JM_*_HE.cfg`.
- Don't change lambda-related fields in `configs/hm/`, `configs/vtm/`,
  `configs/ecm/`.
- Any change to lambda must be documented in both `docs/JM_CTC_alignment.md`
  and `HANDOFF.md` with the rationale.

---

## 6. Extending to full CTC (Class A1/A2 and 10-bit)

When extending to the full CTC after the pilot passes, points to note
about JM:

### 6.1 Adding Class A1/A2 sequences

- Use `cfg/HM-like/per-sequence_JM/{Traffic,PeopleOnStreet,NebutaFestival_10bit,SteamLocomotiveTrain_10bit}.cfg`
  as references.
- Write project-local `configs/sequences/{Traffic,PeopleOnStreet}.yaml`
  (stubs are already present).
- Class A is 2560×1600 @ 30 fps; IntraPeriod is still 32.
- Sequence length is controlled by the sequence YAML; CTC recommends
  150 frames.

### 6.2 Switching to 10-bit (NebutaFestival, SteamLocomotiveTrain)

For JM HM-like, change:

```
ProfileIDC            = 110     # High 10 (replacing 100)
SourceBitDepthLuma    = 10
SourceBitDepthChroma  = 10
OutputBitDepthLuma    = 10
OutputBitDepthChroma  = 10
InternalBitDepth      = 10      # already 10
```

For HM/VTM/ECM, use `encoder_intra_main10.cfg` / `encoder_randomaccess_main10.cfg`
(HM has the 10-bit variants; VTM/ECM Main 10 is the default).

### 6.3 Enabling LDB / LDP configurations

Uncomment LDB / LDP in `configs/pilot.yaml`:

```yaml
configs:
  - AI
  - RA
  - LDB    # uncomment
  - LDP    # uncomment
```

`run_pilot.py` automatically maps these to:

- JM: `encoder_JM_LB_HE.cfg` / `encoder_JM_LP_HE.cfg`
- HM: `encoder_lowdelay_main.cfg` / `encoder_lowdelay_P_main.cfg`
- VTM: `encoder_lowdelay_vtm.cfg` / `encoder_lowdelay_P_vtm.cfg`
- ECM: `encoder_lowdelay_ecm.cfg` / `encoder_lowdelay_P_ecm.cfg`

---

## 7. Sanity check: does the JM result look reasonable?

For CTC RA + BasketballDrill (832×480 @ 50fps) 64 frames at QP=32, a typical
JM output is roughly:

| Metric | Expected range (QP=32) |
|---|---|
| Bitrate | 800–1500 kbps |
| Y-PSNR | 34–37 dB |
| vs HM (same conditions) | HM saves ~35–45% bitrate |

If JM **saves more bits than HM** or has higher PSNR, **investigate
immediately**:

1. Is JM actually using `HierarchicalCoding = 3` and `HM50RefStructure = 1`?
2. Is JM's `IntraPeriod` aligned with HM?
3. Is JM accidentally using `encoder_baseline.cfg` or
   `encoder_max_performance.cfg` instead of HM-like?

---

## 8. References

- JM source: `tools/JM-JM-19.1/cfg/HM-like/README*` and `JM-19.1/CHANGES.TXT`
- HM CTC: JCTVC-L1100, *Common Test Conditions and Software Reference
  Configurations*
- VTM CTC: JVET-Y2010 and successors
- ECM CTC: latest JVET meeting outputs (paired with the ECM tag's software
  guidelines)
- Ohm, Sullivan, Schwarz, Tan, Wiegand, *Comparison of the Coding
  Efficiency of Video Coding Standards — Including HEVC*, IEEE TCSVT,
  Vol. 22, No. 12, Dec. 2012.
