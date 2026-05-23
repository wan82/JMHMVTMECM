#!/usr/bin/env python3
"""Parse encoder logs from the latest run and emit results/raw_metrics.csv.

Handles two log dialects:
  - JM (lencod) — looks for "Total bits", "SNR Y(dB)" summary section.
  - HM / VTM / ECM — looks for "SUMMARY ---" block with PSNR per channel.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = PROJECT_ROOT / "runs"
RESULTS_DIR = PROJECT_ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)


# --- HM / VTM / ECM log patterns ---
# Two formats observed across encoder generations:
#
# HM 18 (single SUMMARY block):
#   SUMMARY --------------------------------------------------------
#         Total Frames |   Bitrate     Y-PSNR    U-PSNR    V-PSNR  ...
#                  64 a   1583.4500   35.7689   38.6314   38.9952  ...
#
# VTM 23 / ECM 18 (per-layer block, no "SUMMARY ---" preamble):
#   LayerId  0
#    Total Frames |  Bitrate      Y-PSNR   U-PSNR   V-PSNR   YUV-PSNR
#   64           a  20580.7438    41.7798  43.8483  44.4565  42.4336
#
# We match the shared "Total Frames | Bitrate ... Y-PSNR ..." header line and
# pull the numbers from the data row that immediately follows. This handles
# both dialects with a single regex.
RE_HM_SUMMARY = re.compile(
    r"Total Frames\s*\|\s*Bitrate\s+Y-PSNR\s+U-PSNR\s+V-PSNR[^\n]*\n"
    r"\s*(\d+)\s+\S+\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)"
)
RE_HM_TIME = re.compile(r"Total Time:\s*([\d.]+)\s*sec\.", re.IGNORECASE)


# --- JM log patterns ---
# JM 19 prints, in the "Average data all frames" trailer:
#    Y { PSNR (dB), cSNR (dB), MSE }   : {  41.514,  41.514,   4.58828 }
#    U { PSNR (dB), cSNR (dB), MSE }   : {  43.824,  43.823,   2.69608 }
#    V { PSNR (dB), cSNR (dB), MSE }   : {  44.484,  44.482,   2.31678 }
#    Total encoding time for the seq.  :  78.916 sec (0.81 fps)
#    Bit rate (kbit/s)  @ 50.00 Hz     : 26802.38
#    Total Frames:  64
# Note word order: "Y { PSNR (dB)" — channel letter comes BEFORE the word PSNR
# (unlike HM/VTM/ECM). First number inside the braces is the PSNR.
RE_JM_PSNR_Y = re.compile(
    r"^\s*Y\s*\{\s*PSNR\s*\(dB\)[^:]*:\s*\{\s*([\d.]+)", re.MULTILINE)
RE_JM_PSNR_U = re.compile(
    r"^\s*U\s*\{\s*PSNR\s*\(dB\)[^:]*:\s*\{\s*([\d.]+)", re.MULTILINE)
RE_JM_PSNR_V = re.compile(
    r"^\s*V\s*\{\s*PSNR\s*\(dB\)[^:]*:\s*\{\s*([\d.]+)", re.MULTILINE)
RE_JM_BITRATE = re.compile(
    r"Bit\s*rate.*kbit.*?[:|]\s*([\d.]+)", re.IGNORECASE)
RE_JM_TIME = re.compile(
    r"Total encoding time.*?[:|]\s*([\d.:]+)", re.IGNORECASE)
# JM prints "Total Frames:  64" (note capital F, colon, no "coded"). The older
# "Total frames coded" wording does not appear in JM 19 output.
RE_JM_FRAMES = re.compile(
    r"Total\s*Frames\s*[:|]\s*(\d+)", re.IGNORECASE)


def parse_jm_time(s: str) -> float:
    """JM may print h:mm:ss or seconds. Return seconds."""
    if ":" in s:
        parts = [float(x) for x in s.split(":")]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
    return float(s)


def parse_hm_like(text: str) -> dict | None:
    m = RE_HM_SUMMARY.search(text)
    if not m:
        return None
    frames = int(m.group(1))
    bitrate_kbps = float(m.group(2))
    y = float(m.group(3))
    u = float(m.group(4))
    v = float(m.group(5))
    time_match = RE_HM_TIME.search(text)
    enc_time = float(time_match.group(1)) if time_match else float("nan")
    return {
        "frames_encoded": frames,
        "bitrate_kbps": bitrate_kbps,
        "psnr_y_db": y,
        "psnr_u_db": u,
        "psnr_v_db": v,
        "enc_time_sec": enc_time,
    }


def parse_jm(text: str) -> dict | None:
    y = RE_JM_PSNR_Y.search(text)
    u = RE_JM_PSNR_U.search(text)
    v = RE_JM_PSNR_V.search(text)
    br = RE_JM_BITRATE.search(text)
    if not (y and br):
        return None
    t = RE_JM_TIME.search(text)
    fr = RE_JM_FRAMES.search(text)
    return {
        "frames_encoded": int(fr.group(1)) if fr else -1,
        "bitrate_kbps": float(br.group(1)),
        "psnr_y_db": float(y.group(1)),
        "psnr_u_db": float(u.group(1)) if u else float("nan"),
        "psnr_v_db": float(v.group(1)) if v else float("nan"),
        "enc_time_sec": parse_jm_time(t.group(1)) if t else float("nan"),
    }


def parse_log(encoder: str, path: Path) -> dict | None:
    text = path.read_text(errors="replace")
    if encoder == "jm":
        return parse_jm(text)
    return parse_hm_like(text)


def latest_run() -> Path:
    runs = sorted([p for p in RUNS_DIR.glob("*") if p.is_dir()],
                  key=lambda p: p.stat().st_mtime, reverse=True)
    if not runs:
        raise FileNotFoundError("No runs found under runs/")
    return runs[0]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", type=str, default=None,
                    help="Run directory name (default: latest).")
    ap.add_argument("--output", type=str,
                    default=str(RESULTS_DIR / "raw_metrics.csv"),
                    help="Output CSV path.")
    args = ap.parse_args()

    run_dir = (RUNS_DIR / args.run_id) if args.run_id else latest_run()
    print(f"Parsing logs in: {run_dir}")
    jobs_csv = run_dir / "jobs.csv"
    if not jobs_csv.exists():
        print(f"ERROR: {jobs_csv} not found", file=sys.stderr)
        return 1

    rows = []
    skipped = 0
    with open(jobs_csv, "r") as f:
        for j in csv.DictReader(f):
            if j["status"] != "DONE":
                skipped += 1
                continue
            log_path = Path(j["log_path"])
            if not log_path.exists():
                print(f"WARN: missing log {log_path}", file=sys.stderr)
                skipped += 1
                continue
            parsed = parse_log(j["encoder"], log_path)
            if parsed is None:
                print(f"WARN: could not parse {log_path}", file=sys.stderr)
                skipped += 1
                continue
            rows.append({
                "job_id": j["job_id"],
                "encoder": j["encoder"],
                "sequence": j["sequence"],
                "config": j["config"],
                "qp": int(j["qp"]),
                **parsed,
            })

    fieldnames = ["job_id", "encoder", "sequence", "config", "qp",
                  "frames_encoded", "bitrate_kbps",
                  "psnr_y_db", "psnr_u_db", "psnr_v_db",
                  "enc_time_sec"]
    with open(args.output, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"Parsed {len(rows)} rows (skipped {skipped}) -> {args.output}")

    # Quick monotonicity sanity
    issues = 0
    by_key: dict[tuple, list[tuple]] = {}
    for r in rows:
        key = (r["encoder"], r["sequence"], r["config"])
        by_key.setdefault(key, []).append(
            (r["qp"], r["bitrate_kbps"], r["psnr_y_db"]))
    for key, pts in by_key.items():
        pts.sort()
        for i in range(1, len(pts)):
            if pts[i][1] >= pts[i - 1][1]:
                print(f"WARN: non-monotone bitrate vs QP for {key}: {pts}",
                      file=sys.stderr)
                issues += 1
                break
    if issues == 0:
        print("Sanity: bitrate-vs-QP monotonicity OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
