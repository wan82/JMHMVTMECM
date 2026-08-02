#!/usr/bin/env python3
"""Run the pilot encoding matrix.

Reads configs/pilot.yaml and configs/sequences/*.yaml, expands to a job matrix
(encoder × sequence × config × QP), and executes jobs with a process pool.

Designed to be resumable: jobs already marked DONE in the run's jobs.csv are
skipped on re-invocation.

Usage:
    python scripts/run_pilot.py                # run all pending jobs
    python scripts/run_pilot.py --dry-run      # print matrix, don't execute
    python scripts/run_pilot.py --jobs 1       # override parallelism
    python scripts/run_pilot.py --run-id X     # resume an existing run
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import shlex
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BIN_DIR = PROJECT_ROOT / "bin"
CONFIGS_DIR = PROJECT_ROOT / "configs"
SEQUENCES_DIR = PROJECT_ROOT / "sequences"
RUNS_DIR = PROJECT_ROOT / "runs"

# Base directory for input YUVs. Sequence YAMLs store only the bare filename,
# resolved under $YUV_DIR — so no machine-specific absolute path is committed.
# Defaults to the project's sequences/ dir; e.g. `export YUV_DIR=/data/yuv`.
YUV_DIR = Path(os.environ["YUV_DIR"]) if os.environ.get("YUV_DIR") else SEQUENCES_DIR


def resolve_yuv(seq: dict) -> Path:
    """Resolve a sequence's input YUV path. An absolute yuv_filename is used
    as-is; a bare filename is resolved under YUV_DIR (default sequences/)."""
    p = Path(seq["yuv_filename"])
    return p if p.is_absolute() else (YUV_DIR / seq["yuv_filename"])

# Maps the abstract config name (AI/RA/LDB/LDP) to each encoder's cfg filename.
CONFIG_MAP = {
    "AI":  {"jm": "encoder_JM_Intra_HE.cfg",
            "hm": "encoder_intra_main.cfg",
            "vtm": "encoder_intra_vtm.cfg",
            "ecm": "encoder_intra_ecm.cfg"},
    "RA":  {"jm": "encoder_JM_RA_B_HE.cfg",
            "hm": "encoder_randomaccess_main.cfg",
            "vtm": "encoder_randomaccess_vtm.cfg",
            "ecm": "encoder_randomaccess_ecm.cfg"},
    "LDB": {"jm": "encoder_JM_LB_HE.cfg",
            "hm": "encoder_lowdelay_main.cfg",
            "vtm": "encoder_lowdelay_vtm.cfg",
            "ecm": "encoder_lowdelay_ecm.cfg"},
    "LDP": {"jm": "encoder_JM_LP_HE.cfg",
            "hm": "encoder_lowdelay_P_main.cfg",
            "vtm": "encoder_lowdelay_P_vtm.cfg",
            "ecm": "encoder_lowdelay_P_ecm.cfg"},
}

# Binary name produced by build_all.sh
BIN_MAP = {
    "jm":  "lencod",
    "hm":  "TAppEncoder",
    "vtm": "EncoderApp_VTM",
    "ecm": "EncoderApp_ECM",
}


# --- IntraPeriod policy (CTC) ---
def ctc_intra_period(fps: float) -> int:
    """CTC IntraPeriod recommendation by frame rate."""
    if fps >= 55:
        return 64
    return 32


# --- Job model ---
@dataclass
class Job:
    job_id: str
    encoder: str
    sequence: str
    config: str
    qp: int
    cmd: list[str] = field(default_factory=list)
    log_path: str = ""
    bitstream_path: str = ""
    status: str = "PENDING"
    start_time: str = ""
    end_time: str = ""
    exit_code: int = -1


def load_pilot_config() -> dict:
    with open(CONFIGS_DIR / "pilot.yaml", "r") as f:
        return yaml.safe_load(f)


def load_sequence(name: str) -> dict:
    p = CONFIGS_DIR / "sequences" / f"{name}.yaml"
    if not p.exists():
        raise FileNotFoundError(f"Sequence config missing: {p}")
    with open(p, "r") as f:
        return yaml.safe_load(f)


def make_run_dir(pilot_cfg: dict, run_id: str | None,
                 run_name: str | None = None) -> Path:
    if run_id:
        run_dir = RUNS_DIR / run_id
        if not run_dir.exists():
            raise FileNotFoundError(f"Run dir not found: {run_dir}")
        return run_dir
    if run_name:
        # Fixed, caller-chosen directory (e.g. one per sequence for concurrent
        # windows). Created if absent, reused if present (so a re-run resumes).
        run_dir = RUNS_DIR / run_name
    else:
        stamp = dt.datetime.now().strftime(
            pilot_cfg.get("run_dir_pattern", "%Y-%m-%d_%H%M_pilot"))
        run_dir = RUNS_DIR / stamp
    for sub in ("bitstreams", "logs", "tmp_configs"):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)
    return run_dir


# JVET VVC CTC AI subsample ratio. Must match TSR used by
# scripts/extract_ai_subsample.py. AI is all-intra so adjacent frames give
# near-identical RD numbers — sampling every 8th is the JVET convention.
AI_TSR = 8

# Extra CLI args appended to ECM commands only (set from --extra-ecm-args in
# main()). Used to disable a buggy ECM tool per-run without editing the shared
# cfg, e.g. "--GeoBlendIntra=0". Applied at command-build time in the main
# process, so a plain module global is safe (workers get the finished command).
EXTRA_ECM_ARGS: list[str] = []


# --- ECM official per-class CTC layering ---
# JVET CTC tunes CTUSize + MTT depths per resolution class. ECM ships these in
# cfg/per-class/class{A,B,C,D}_randomaccess.cfg; we mirror them under
# configs/ecm/per-class/. They are layered ON TOP of the base RA cfg (a second
# `-c`, so their CTUSize/MTT win over the base) for ECM RA jobs only. This is
# what makes Class A run at CTUSize 256 (its official value) instead of the base
# 128 — and is exactly the config a proper VTM-vs-ECM cross-gen comparison needs.
# VTM has no 256-CTU support and rejects some ECM-only keys in these files, so it
# is never layered (VTM already runs its correct 128-CTU CTC via its own base).
# Sequence `class` A1/A2 both map to per-class file A (JVET groups both under
# Class A / 4K); B/C/D map 1:1.
CLASS_TO_PERCLASS = {"A1": "A", "A2": "A", "A": "A", "B": "B", "C": "C", "D": "D"}


def ecm_per_class_cfg(seq: dict) -> Path | None:
    """Return the ECM per-class RA cfg for this sequence's class, or None if the
    class is unknown or the file is absent (caller then falls back to base only)."""
    letter = CLASS_TO_PERCLASS.get(str(seq.get("class", "")).strip())
    if not letter:
        return None
    p = CONFIGS_DIR / "ecm" / "per-class" / f"class{letter}_randomaccess.cfg"
    return p if p.exists() else None


# --- Per-encoder command builders ---
def build_cmd_hm_vtm_ecm(enc: str, seq: dict, cfg_name: str, qp: int,
                         frames: int, intra_period: int, run_dir: Path,
                         job_id: str) -> tuple[list[str], Path, Path]:
    binary = BIN_DIR / BIN_MAP[enc]
    enc_cfg = CONFIGS_DIR / enc / CONFIG_MAP[cfg_name][enc]
    yuv_path = resolve_yuv(seq)
    bs_path = run_dir / "bitstreams" / f"{job_id}.bin"
    log_path = run_dir / "logs" / f"{job_id}.log"

    # AI mode: every frame is intra, IntraPeriod must be 1.
    # The encoder_intra_*.cfg files already set IntraPeriod=1, but we override
    # explicitly so the CLI is self-documenting and so re-using a RA-style
    # cfg by mistake won't silently produce wrong results.
    effective_intra_period = 1 if cfg_name == "AI" else intra_period

    cmd = [
        str(binary),
        "-c", str(enc_cfg),
    ]
    # ECM RA: layer the official per-class CTC cfg (CTUSize/MTT per resolution
    # class) as a second `-c` so it overrides the base. RA-only: the per-class
    # files are random-access tunings. VTM/HM never get this (see note above).
    if enc == "ecm" and cfg_name == "RA":
        per_class = ecm_per_class_cfg(seq)
        if per_class is not None:
            cmd += ["-c", str(per_class)]
    cmd += [
        f"--InputFile={yuv_path}",
        f"--BitstreamFile={bs_path}",
        f"--SourceWidth={seq['width']}",
        f"--SourceHeight={seq['height']}",
        f"--FrameRate={seq['fps']}",
        f"--InputBitDepth={seq['bit_depth']}",
        f"--InputChromaFormat={seq['chroma_format']}",
        f"--FramesToBeEncoded={frames}",
        f"--FrameSkip=0",
        f"--QP={qp}",
        f"--IntraPeriod={effective_intra_period}",
        f"--Level={seq.get('level', '5.1')}",
        "--ReconFile=",  # empty = no recon written
    ]
    # AI mode: follow JVET VVC CTC methodology — encode every AI_TSR-th frame
    # within the FramesToBeEncoded window. HM 18.0, VTM 23, ECM 18 all accept
    # this CLI override. With FramesToBeEncoded=64 and TSR=8, the encoder reads
    # frames 0..63 of the YUV and emits 8 encoded pictures (POC 0..7
    # corresponding to source frames 0, 8, 16, ..., 56). The reported bitrate
    # is divided by source_fps/TSR (e.g. 6.25Hz for 50fps content) so kbps
    # remain meaningful at the encoded-picture time base.
    if cfg_name == "AI":
        cmd.append(f"--TemporalSubsampleRatio={AI_TSR}")
    # ECM-only extra args (e.g. disabling a buggy tool). VTM rejects unknown
    # options, so never append these to VTM/HM.
    if enc == "ecm" and EXTRA_ECM_ARGS:
        cmd += EXTRA_ECM_ARGS
    return cmd, bs_path, log_path


def build_cmd_jm(seq: dict, cfg_name: str, qp: int, frames: int,
                 intra_period: int, run_dir: Path, job_id: str) -> tuple[list[str], Path, Path]:
    binary = BIN_DIR / BIN_MAP["jm"]
    enc_cfg = CONFIGS_DIR / "jm" / CONFIG_MAP[cfg_name]["jm"]
    bs_path = run_dir / "bitstreams" / f"{job_id}.264"
    log_path = run_dir / "logs" / f"{job_id}.log"

    # JM has no TemporalSubsampleRatio option, so for AI we feed it a
    # pre-decimated YUV produced by scripts/extract_ai_subsample.py
    # (containing only source frames 0, AI_TSR, 2*AI_TSR, ...). To keep the
    # output kbps on the same time base as HM/VTM/ECM (which divide by
    # source_fps/TSR), we lie to JM about FrameRate: tell it fps/TSR.
    if cfg_name == "AI":
        src_yuv = resolve_yuv(seq)
        sub_yuv = src_yuv.with_name(src_yuv.stem + f"_AI_TSR{AI_TSR}.yuv")
        if not sub_yuv.exists():
            raise FileNotFoundError(
                f"Missing subsampled AI YUV: {sub_yuv}. "
                f"Run: python scripts/extract_ai_subsample.py")
        yuv_path = sub_yuv
        encoded_frames = frames // AI_TSR
        framerate = seq["fps"] / AI_TSR  # may be fractional, JM accepts that
    else:
        yuv_path = resolve_yuv(seq)
        encoded_frames = frames
        framerate = seq["fps"]

    # JM IDRPeriod also needs to be set for RA; for AI both should be 1
    idr_period = 1 if cfg_name == "AI" else intra_period

    # Build -p key=value override list. Spaces are not allowed inside -p arg.
    overrides = [
        f"InputFile={yuv_path}",
        f"OutputFile={bs_path}",
        "ReconFile=",
        f"SourceWidth={seq['width']}",
        f"SourceHeight={seq['height']}",
        f"OutputWidth={seq['width']}",
        f"OutputHeight={seq['height']}",
        f"FrameRate={framerate}",
        f"FramesToBeEncoded={encoded_frames}",
        "FrameSkip=0",
        f"SourceBitDepthLuma={seq['bit_depth']}",
        f"SourceBitDepthChroma={seq['bit_depth']}",
        f"OutputBitDepthLuma={seq['bit_depth']}",
        f"OutputBitDepthChroma={seq['bit_depth']}",
        f"QPISlice={qp}",
        f"QPPSlice={qp}",
        f"QPBSlice={qp}",
        f"IntraPeriod={1 if cfg_name == 'AI' else intra_period}",
        f"IDRPeriod={idr_period}",
    ]

    cmd = [str(binary), "-d", str(enc_cfg)]
    for kv in overrides:
        cmd += ["-p", kv]
    return cmd, bs_path, log_path


def build_command(job: Job, seq: dict, frames: int, intra_period: int,
                  run_dir: Path) -> tuple[list[str], Path, Path]:
    if job.encoder == "jm":
        return build_cmd_jm(seq, job.config, job.qp, frames, intra_period,
                            run_dir, job.job_id)
    elif job.encoder in ("hm", "vtm", "ecm"):
        return build_cmd_hm_vtm_ecm(job.encoder, seq, job.config, job.qp,
                                    frames, intra_period, run_dir, job.job_id)
    raise ValueError(f"Unknown encoder: {job.encoder}")


# --- Head-frames mode helpers ---
# In head-frames mode (`make encode N` / --coded-frames N) the two expensive
# VVC-family encoders (VTM, ECM) are stopped after the first N pictures in
# CODING order. For a GOP-32 RA hierarchy N=7 gives POC {0,32,16,8,4,2,1} — the
# I-frame plus one picture per temporal layer. The stop happens inside the
# encoder itself (a patched EncGOP.cpp reads PILOT_MAX_CODED_PICS); here we only
# set that env var. JM and HM are cheap, so they keep encoding in full with
# their own native GOP (no env var, no cap).
def job_env(job: Job, coded_frames: int) -> dict:
    if coded_frames > 0 and job.encoder in ("vtm", "ecm"):
        return {"PILOT_MAX_CODED_PICS": str(coded_frames)}
    return {}


def apply_seq_overrides(seq: dict, args) -> None:
    """Apply CLI geometry/input overrides onto a loaded sequence dict, in place.

    --input may be an absolute path (used as-is: `SEQUENCES_DIR / abspath` keeps
    the abspath) or a bare filename resolved under sequences/.
    """
    if getattr(args, "input", None):
        seq["yuv_filename"] = args.input
    if getattr(args, "width", None):
        seq["width"] = args.width
    if getattr(args, "height", None):
        seq["height"] = args.height
    if getattr(args, "fps", None):
        seq["fps"] = args.fps
    if getattr(args, "bit_depth", None):
        seq["bit_depth"] = args.bit_depth


# --- Matrix expansion ---
def expand_matrix(pilot_cfg: dict, run_dir: Path) -> list[Job]:
    jobs = []
    counter = 0
    for enc in pilot_cfg["encoders"]:
        for seq_name in pilot_cfg["sequences"]:
            for cfg_name in pilot_cfg["configs"]:
                for qp in pilot_cfg["qps"]:
                    counter += 1
                    jid = f"{counter:04d}_{enc}_{seq_name}_{cfg_name}_QP{qp}"
                    jobs.append(Job(
                        job_id=jid,
                        encoder=enc,
                        sequence=seq_name,
                        config=cfg_name,
                        qp=qp,
                    ))
    return jobs


# --- Persistence of job state ---
JOBS_CSV_HEADER = [
    "job_id", "encoder", "sequence", "config", "qp",
    "status", "start_time", "end_time", "exit_code",
    "log_path", "bitstream_path",
]


def write_jobs_csv(run_dir: Path, jobs: list[Job]) -> None:
    p = run_dir / "jobs.csv"
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=JOBS_CSV_HEADER)
        w.writeheader()
        for j in jobs:
            d = asdict(j)
            d.pop("cmd", None)
            w.writerow({k: d[k] for k in JOBS_CSV_HEADER})


def read_jobs_csv(run_dir: Path) -> list[Job]:
    p = run_dir / "jobs.csv"
    if not p.exists():
        return []
    out = []
    with open(p, "r") as f:
        r = csv.DictReader(f)
        for row in r:
            out.append(Job(
                job_id=row["job_id"],
                encoder=row["encoder"],
                sequence=row["sequence"],
                config=row["config"],
                qp=int(row["qp"]),
                status=row.get("status", "PENDING"),
                start_time=row.get("start_time", ""),
                end_time=row.get("end_time", ""),
                exit_code=int(row.get("exit_code", -1) or -1),
                log_path=row.get("log_path", ""),
                bitstream_path=row.get("bitstream_path", ""),
            ))
    return out


def update_job_status(run_dir: Path, job: Job) -> None:
    """Rewrite the entire jobs.csv with the updated job. Cheap for ~100 rows."""
    jobs = read_jobs_csv(run_dir)
    by_id = {j.job_id: j for j in jobs}
    by_id[job.job_id] = job
    write_jobs_csv(run_dir, list(by_id.values()))


# --- Worker ---
def run_one_job(args: tuple) -> tuple[str, int, str]:
    """Top-level worker (must be picklable for ProcessPoolExecutor)."""
    job_id, cmd, log_path, timeout_sec, env_extra = args
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(env_extra or {})
    start = time.time()
    try:
        with open(log_path, "w") as logf:
            logf.write("# CMD: " + " ".join(shlex.quote(c) for c in cmd) + "\n")
            if env_extra:
                logf.write("# ENV: " + " ".join(f"{k}={v}"
                                                for k, v in env_extra.items()) + "\n")
            logf.flush()
            proc = subprocess.run(
                cmd,
                stdout=logf,
                stderr=subprocess.STDOUT,
                timeout=timeout_sec if timeout_sec > 0 else None,
                env=env,
            )
        elapsed = time.time() - start
        return job_id, proc.returncode, f"elapsed={elapsed:.1f}s"
    except subprocess.TimeoutExpired:
        return job_id, 124, "TIMEOUT"
    except Exception as e:  # noqa: BLE001
        return job_id, 1, f"EXCEPTION: {e}"


# --- Main ---
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="Print job matrix and commands but don't execute.")
    ap.add_argument("--jobs", type=int, default=None,
                    help="Override parallel_jobs from pilot.yaml.")
    ap.add_argument("--run-id", type=str, default=None,
                    help="Resume an existing run directory by name.")
    ap.add_argument("--run-name", type=str, default=None,
                    help="Use a fixed run directory runs/<name> (created if "
                         "absent, resumed if present). Lets concurrent "
                         "invocations (e.g. one window per sequence) avoid "
                         "clobbering each other's jobs.csv.")
    ap.add_argument("--coded-frames", type=int, default=0, metavar="N",
                    help="Head-frames mode: cap VTM/ECM to the first N pictures "
                         "in CODING order (N=7 -> POC 0,32,16,8,4,2,1 for GOP-32 "
                         "RA), then exit. Forces RA config; JM/HM still encode in "
                         "full. 0 = disabled (normal matrix).")
    ap.add_argument("--qp", type=int, default=None,
                    help="Override the QP list with a single QP.")
    ap.add_argument("--seq", type=str, default=None,
                    help="Override the sequence list with a single sequence name.")
    ap.add_argument("--input", type=str, default=None,
                    help="Override the input YUV path (absolute, or a bare "
                         "filename under sequences/).")
    ap.add_argument("--width", type=int, default=None, help="Override source width.")
    ap.add_argument("--height", type=int, default=None, help="Override source height.")
    ap.add_argument("--fps", type=float, default=None, help="Override frame rate.")
    ap.add_argument("--bit-depth", type=int, default=None,
                    help="Override input bit depth.")
    ap.add_argument("--encoders", type=str, default=None,
                    help="Comma-separated encoder subset, e.g. vtm,ecm.")
    ap.add_argument("--extra-ecm-args", type=str, default="",
                    help="Extra CLI args appended to ECM commands only, e.g. "
                         "\"--GeoBlendIntra=0\" to disable a buggy ECM tool for "
                         "a re-run without touching the shared cfg.")
    args = ap.parse_args()

    pilot_cfg = load_pilot_config()
    coded_frames = max(0, args.coded_frames)

    global EXTRA_ECM_ARGS
    if args.extra_ecm_args:
        EXTRA_ECM_ARGS = shlex.split(args.extra_ecm_args)

    # --- CLI overrides on top of pilot.yaml ---
    if args.encoders:
        pilot_cfg["encoders"] = [e.strip() for e in args.encoders.split(",")
                                 if e.strip()]
    if args.seq:
        pilot_cfg["sequences"] = [args.seq]
    if args.qp is not None:
        pilot_cfg["qps"] = [args.qp]

    if coded_frames > 0:
        # Head-frames mode is RA-only by definition ("normal RA encode, stopped
        # after N coded pictures"). Force RA regardless of pilot.yaml.
        pilot_cfg["configs"] = ["RA"]
        # VTM/ECM must READ enough input frames for the GOP-32 anchor (POC 32) to
        # exist, otherwise the hierarchy degrades. The in-encoder counter then
        # stops coding at N. 64 (2 GOPs) is always enough and cheap (extra frames
        # are only read, never coded). Never shrink below the configured window.
        pilot_cfg["frames_to_encode"] = max(
            int(pilot_cfg.get("frames_to_encode", 64)), 64)
        print(f"[head-frames] VTM/ECM capped to first {coded_frames} coded "
              f"pictures (RA); JM/HM encode in full.")

    parallel = args.jobs if args.jobs is not None else pilot_cfg["parallel_jobs"]
    timeout_sec = int(pilot_cfg.get("job_timeout_sec", 0))
    frames = int(pilot_cfg["frames_to_encode"])

    # Sanity: binaries exist (skip in dry-run)
    if not args.dry_run:
        for enc in pilot_cfg["encoders"]:
            b = BIN_DIR / BIN_MAP[enc]
            if not b.exists():
                print(f"ERROR: missing binary {b}. Run `make build` first.",
                      file=sys.stderr)
                return 2

    run_dir = make_run_dir(pilot_cfg, args.run_id, args.run_name)
    print(f"Run directory: {run_dir}")

    # Build matrix (or load if resuming)
    if (args.run_id or args.run_name) and (run_dir / "jobs.csv").exists():
        jobs = read_jobs_csv(run_dir)
        print(f"Resuming run with {len(jobs)} known jobs")
    else:
        jobs = expand_matrix(pilot_cfg, run_dir)
        write_jobs_csv(run_dir, jobs)

    # Compute commands now (also used by dry-run)
    seq_cache: dict[str, dict] = {}
    runnable = []
    for j in jobs:
        if j.sequence not in seq_cache:
            s = load_sequence(j.sequence)
            apply_seq_overrides(s, args)
            seq_cache[j.sequence] = s
        seq = seq_cache[j.sequence]
        ip = ctc_intra_period(seq["fps"])
        cmd, bs_path, log_path = build_command(j, seq, frames, ip, run_dir)
        j.cmd = cmd
        j.bitstream_path = str(bs_path)
        j.log_path = str(log_path)
        runnable.append(j)

    # Dry run: just print
    if args.dry_run:
        print(f"\nTotal jobs: {len(runnable)}")
        for j in runnable:
            print(f"\n# {j.job_id} [{j.status}]")
            env_extra = job_env(j, coded_frames)
            if env_extra:
                print("  ENV: " + " ".join(f"{k}={v}"
                                           for k, v in env_extra.items()))
            print("  " + " ".join(shlex.quote(c) for c in j.cmd))
        return 0

    # Filter out already-DONE jobs
    pending = [j for j in runnable if j.status != "DONE"]
    print(f"Pending: {len(pending)} / Total: {len(runnable)} (parallel={parallel})")

    # Sort by predicted cost (cheap first): jm < hm < vtm < ecm
    cost_order = {"jm": 0, "hm": 1, "vtm": 2, "ecm": 3}
    pending.sort(key=lambda j: (cost_order.get(j.encoder, 9), j.config, j.qp))

    # Mark RUNNING
    for j in pending:
        j.status = "RUNNING"
        j.start_time = dt.datetime.now().isoformat(timespec="seconds")
    write_jobs_csv(run_dir, runnable)

    # Submit
    payloads = [(j.job_id, j.cmd, j.log_path, timeout_sec,
                 job_env(j, coded_frames)) for j in pending]
    by_id = {j.job_id: j for j in runnable}

    completed = 0
    failed = 0
    total = len(payloads)
    with ProcessPoolExecutor(max_workers=parallel) as ex:
        futures = {ex.submit(run_one_job, p): p[0] for p in payloads}
        for fut in as_completed(futures):
            jid = futures[fut]
            try:
                _, rc, note = fut.result()
            except Exception as e:  # noqa: BLE001
                rc, note = 1, f"EXCEPTION: {e}"
            j = by_id[jid]
            j.exit_code = rc
            j.end_time = dt.datetime.now().isoformat(timespec="seconds")
            j.status = "DONE" if rc == 0 else "FAILED"
            update_job_status(run_dir, j)
            completed += 1
            if rc != 0:
                failed += 1
            print(f"[{completed}/{total}] {jid} -> {j.status} ({note})",
                  flush=True)

    print(f"\nDone. Success: {total - failed}, Failed: {failed}")
    print(f"Logs in: {run_dir / 'logs'}")
    print(f"Job CSV: {run_dir / 'jobs.csv'}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
