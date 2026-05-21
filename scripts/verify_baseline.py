#!/usr/bin/env python3
"""Verify that the latest run reproduces the pilot baseline within tolerance.

Compares results/raw_metrics.csv against results/pilot_baseline.csv on the
3 pilot sequences. Pass criterion: |ΔY-PSNR| < 0.05 dB AND
|Δbitrate| / bitrate_baseline < 1%.

If results/pilot_baseline.csv does not exist (first run), this script just
copies the current raw_metrics.csv as the baseline and exits 0.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "results"
BASELINE_P = RESULTS_DIR / "pilot_baseline.csv"
CURRENT_P = RESULTS_DIR / "raw_metrics.csv"

PSNR_TOL_DB = 0.05
RATE_TOL_FRAC = 0.01


def main() -> int:
    if not CURRENT_P.exists():
        print(f"ERROR: missing {CURRENT_P}", file=sys.stderr)
        return 1
    cur = pd.read_csv(CURRENT_P)
    if not BASELINE_P.exists():
        print(f"No baseline found. Stamping current run as baseline:")
        print(f"  cp {CURRENT_P} -> {BASELINE_P}")
        shutil.copy(CURRENT_P, BASELINE_P)
        return 0

    base = pd.read_csv(BASELINE_P)
    key = ["encoder", "sequence", "config", "qp"]
    merged = cur.merge(base, on=key, suffixes=("_cur", "_base"))
    if merged.empty:
        print("ERROR: no overlapping rows between current and baseline.",
              file=sys.stderr)
        return 1

    merged["psnr_y_diff"] = merged["psnr_y_db_cur"] - merged["psnr_y_db_base"]
    merged["bitrate_diff_frac"] = (
        (merged["bitrate_kbps_cur"] - merged["bitrate_kbps_base"])
        / merged["bitrate_kbps_base"]
    )
    bad_psnr = merged[merged["psnr_y_diff"].abs() > PSNR_TOL_DB]
    bad_rate = merged[merged["bitrate_diff_frac"].abs() > RATE_TOL_FRAC]

    if bad_psnr.empty and bad_rate.empty:
        print(f"BASELINE OK: {len(merged)} rows within tolerance.")
        return 0

    print("BASELINE MISMATCH:")
    if not bad_psnr.empty:
        print(f"  {len(bad_psnr)} rows with |ΔY-PSNR| > {PSNR_TOL_DB} dB:")
        print(bad_psnr[key + ["psnr_y_db_cur", "psnr_y_db_base",
                              "psnr_y_diff"]].to_string(index=False))
    if not bad_rate.empty:
        print(f"  {len(bad_rate)} rows with |Δbitrate|/base > "
              f"{RATE_TOL_FRAC * 100}%:")
        print(bad_rate[key + ["bitrate_kbps_cur", "bitrate_kbps_base",
                              "bitrate_diff_frac"]].to_string(index=False))
    return 1


if __name__ == "__main__":
    sys.exit(main())
