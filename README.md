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
