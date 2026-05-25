# 00 — Project Overview

> This document explains what the project is about, why it is designed this
> way, where it fits in the paper landscape, and the trade-offs made in the
> pilot phase.
> After reading this you should be able to answer in 5 minutes: "What is this
> repo for? Why is it set up this way?"

---

## 1. Origin of the project

The advisor proposed a conference-paper direction: a horizontal comparison
of the **reference software** for four generations of video coding standards,
to quantify how compression efficiency and encoding complexity have evolved
from H.264/AVC to the post-VVC exploration in development today.

Four standards and their reference software:

| Standard | Year finalised | Reference software | Maintainer |
|---|---|---|---|
| H.264 / MPEG-4 AVC | 2003 | **JM** (Joint Model) | Fraunhofer HHI |
| H.265 / HEVC | 2013 | **HM** (HEVC test Model) | JCT-VC |
| H.266 / VVC | 2020 | **VTM** (VVC Test Model) | JVET |
| (post-VVC, unnamed) | in development | **ECM** (Enhanced Compression Model) | JVET |

Each generation is roughly 7–10 years apart, and each one claims "~50% bitrate
savings at equal PSNR" over its predecessor. That figure appears repeatedly
in JVET's official reports, but **always as isolated pairwise comparisons** —
there is no unified, methodologically consistent four-generation horizontal
view. That is the gap this project fills.

## 2. The methodological reference

The canonical paper for this kind of horizontal comparison is:

> Ohm, Sullivan, Schwarz, Tan, Wiegand,
> *Comparison of the Coding Efficiency of Video Coding Standards — Including HEVC*,
> IEEE Trans. on Circuits and Systems for Video Technology, Vol. 22, No. 12,
> Dec. 2012.

It compared five generations (MPEG-2 / H.263 / MPEG-4 / AVC / HEVC) under a
unified methodology and set the standard pattern for this kind of work:

- **Do not unify each encoder's internal lambda / RDO formula** — every
  generation's lambda has been retuned by its developers as the local optimum
  for that generation's tool set.
- **Unify the external test protocol**: same sequences, same QP set, equivalent
  GOP structure, same IntraPeriod.
- **Measure the gap via BD-rate**: for each (sequence, config), sweep 4 QPs,
  fit RD curves, and compare the bitrate distance between curves.

This project inherits that methodology and **extends it from 5 generations to 7**
(adding VVC and ECM, retiring the now-obsolete MPEG-2/H.263). The paper
positioning is essentially "the ECM-era sequel to Ohm 2012."

## 3. Project goals

The end deliverables (what the paper needs to report):

1. **BD-rate table**: per-generation bitrate savings (Y / U / V channels,
   at least AI and RA configurations).
2. **Cumulative BD-rate**: ECM vs JM total — answering "how much have we
   saved over the past two decades from AVC to post-VVC?"
3. **Encoding-time growth curve**: JM → HM → VTM → ECM multipliers. This is
   the paper's differentiating angle; Ohm 2012 did not emphasise this view.
4. **Methodology documentation**: every encoder version, configuration,
   sequence, QP, and frame count is fully reproducible.

Expected magnitudes (extrapolated from published data):

| Comparison | Expected Y-PSNR BD-rate (RA) |
|---|---|
| HM vs JM | -35% to -45% |
| VTM vs HM | -30% to -40% |
| ECM vs VTM | -15% to -25% |
| ECM vs JM (cumulative) | -75% to -85% |

Numbers landing in these ranges are healthy; numbers far outside should
**first be suspected as a pipeline bug**, only second as a configuration issue.

## 4. Pilot vs full CTC

The full JVET CTC covers 7 Classes (A1/A2/B/C/D/E/F), ~20+ sequences,
4 configurations (AI/RA/LDB/LDP), 4 QPs, 4 encoders ≈ **1,280 independent
encoding tasks**. Running this end-to-end on a single Mac Studio M4 Max would
take months, dominated by ECM.

The pilot phase therefore aggressively narrowed the scope:

| Dimension | Pilot | Full CTC (later) |
|---|---|---|
| Test sequences | 2 (Class C + D) | ~20+ (A1/A2/B/C/D/E/F) |
| Max resolution | 832×480 (Class C) | 2560×1600 (Class A) |
| Configurations | AI + RA | + LDB + LDP |
| Frames | 64 (1–2 GOPs) | full sequence length |
| QPs | 22, 27, 32, 37 | same |
| Total encode tasks | 64 | ~1,280 |
| Expected wall-clock | ~1–2 weeks | infeasible on a single machine; needs a cluster |

**The pilot is not meant to produce paper-grade data.** Its goals are:

1. Get the full pipeline (compile → encode → parse → BD-rate → report)
   running end-to-end.
2. Produce a small but trustworthy **baseline** that any future extension
   can regress against.
3. Hand the project off in a clean state to a successor who, after the
   author graduates, will take it through the full CTC.

## 5. Target hardware and team handoff

**Pilot runs on**: Mac Studio (Apple M4 Max, 36 GB RAM, macOS).

- A single machine is sufficient; thermals are excellent and 1–2 weeks of
  continuous load is no problem.
- But **insufficient** for 4K (Class A) or full sequence lengths — those will
  move to a Linux cluster.

A design principle is **first-class support for both macOS and Linux**.
`scripts/build_all.sh` auto-detects the platform, and all Python scripts
avoid any platform-specific APIs. When a successor migrates to a cluster,
they only need to change a few fields in `configs/pilot.yaml` — no code edits.

## 6. The repo's three guiding principles

If you have to summarise the design philosophy in three sentences:

1. **Configs are immutable; runtime injects everything else.** All CTC config
   files are kept exactly as shipped by their maintainers — no per-run values
   (paths, QPs, frame counts) are hard-coded into them. Those are passed via
   the CLI at runtime.
2. **The pilot is a guardrail for everything that comes after.** Pilot data
   is committed as the baseline; any future extension (cluster, new sequence,
   new encoder version) must reproduce the baseline first.
3. **Don't modify upstream encoder source.** JM/HM/VTM/ECM source code is
   never edited. Platform-compatibility fixes (e.g. x86 intrinsics in ECM on
   ARM macOS) live as external patches for traceability and easy rollback.

## 7. Reading order

- This document (00): **Project overview** — why and what.
- [01 Project structure](01_project_structure.md): what each directory and
  each file is for.
- [02 JM config explained](02_jm_config_explained.md): the JM alignment
  details (this is what reviewers are most likely to ask about — required
  reading).
- [03 How to run](03_how_to_run.md): get the pilot running from scratch.

After these four files plus `README.md` and `HANDOFF.md`, you will have a
complete picture of the project.
