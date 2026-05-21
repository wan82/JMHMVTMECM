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


def make_run_dir(pilot_cfg: dict, run_id: str | None) -> Path:
    if run_id:
        run_dir = RUNS_DIR / run_id
        if not run_dir.exists():
            raise FileNotFoundError(f"Run dir not found: {run_dir}")
        return run_dir
    stamp = dt.datetime.now().strftime(pilot_cfg.get("run_dir_pattern", "%Y-%m-%d_%H%M_pilot"))
    run_dir = RUNS_DIR / stamp
    for sub in ("bitstreams", "logs", "tmp_configs"):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)
    return run_dir


# --- Per-encoder command builders ---
def build_cmd_hm_vtm_ecm(enc: str, seq: dict, cfg_name: str, qp: int,
                         frames: int, intra_period: int, run_dir: Path,
                         job_id: str) -> tuple[list[str], Path, Path]:
    binary = BIN_DIR / BIN_MAP[enc]
    enc_cfg = CONFIGS_DIR / enc / CONFIG_MAP[cfg_name][enc]
    yuv_path = SEQUENCES_DIR / seq["yuv_filename"]
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
    return cmd, bs_path, log_path


def build_cmd_jm(seq: dict, cfg_name: str, qp: int, frames: int,
                 intra_period: int, run_dir: Path, job_id: str) -> tuple[list[str], Path, Path]:
    binary = BIN_DIR / BIN_MAP["jm"]
    enc_cfg = CONFIGS_DIR / "jm" / CONFIG_MAP[cfg_name]["jm"]
    yuv_path = SEQUENCES_DIR / seq["yuv_filename"]
    bs_path = run_dir / "bitstreams" / f"{job_id}.264"
    log_path = run_dir / "logs" / f"{job_id}.log"

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
        f"FrameRate={seq['fps']}",
        f"FramesToBeEncoded={frames}",
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
    job_id, cmd, log_path, timeout_sec = args
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    start = time.time()
    try:
        with open(log_path, "w") as logf:
            logf.write("# CMD: " + " ".join(shlex.quote(c) for c in cmd) + "\n")
            logf.flush()
            proc = subprocess.run(
                cmd,
                stdout=logf,
                stderr=subprocess.STDOUT,
                timeout=timeout_sec if timeout_sec > 0 else None,
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
    args = ap.parse_args()

    pilot_cfg = load_pilot_config()
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

    run_dir = make_run_dir(pilot_cfg, args.run_id)
    print(f"Run directory: {run_dir}")

    # Build matrix (or load if resuming)
    if args.run_id and (run_dir / "jobs.csv").exists():
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
            seq_cache[j.sequence] = load_sequence(j.sequence)
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
    payloads = [(j.job_id, j.cmd, j.log_path, timeout_sec) for j in pending]
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
