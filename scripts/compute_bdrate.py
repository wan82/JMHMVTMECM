#!/usr/bin/env python3
"""Compute BD-rate across encoders from results/raw_metrics.csv.

For each (sequence, config) the BD-rate is computed for these pairs:
  - HM vs JM           (HEVC vs AVC)
  - VTM vs HM          (VVC vs HEVC)
  - ECM vs VTM         (post-VVC vs VVC)
  - ECM vs JM          (cumulative)

Output: results/bdrate_table.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "results"

PAIRS = [
    ("hm", "jm",   "HM-vs-JM"),
    ("vtm", "hm",  "VTM-vs-HM"),
    ("ecm", "vtm", "ECM-vs-VTM"),
    ("ecm", "jm",  "ECM-vs-JM"),
]


def bdrate_piecewise_cubic(rate_ref, psnr_ref, rate_test, psnr_test) -> float:
    """BD-rate via Bjontegaard's piecewise cubic interpolation in (logRate, PSNR).

    Returns percentage; negative means test saves bits over ref.
    Prefers the third-party `bjontegaard` package (FAU-LMS, on PyPI) for
    consistency with published implementations. Falls back to a built-in
    cubic-fit if the package is unavailable.
    """
    try:
        import bjontegaard as bd  # type: ignore
        # bjontegaard package: bd.bd_rate(rate_anchor, dist_anchor,
        #                                  rate_test,   dist_test,
        #                                  method='akima'|'cubic'|'pchip')
        # Akima interpolation is the package author's recommended default —
        # more stable than CSI / PCHIP per their docs.
        return float(bd.bd_rate(rate_ref, psnr_ref,
                                rate_test, psnr_test,
                                method='akima'))
    except Exception:
        pass

    # Fallback: 3rd-order log-rate vs PSNR fit (the classical Bjontegaard 2001)
    log_ref = np.log(np.asarray(rate_ref, dtype=float))
    log_test = np.log(np.asarray(rate_test, dtype=float))
    p_ref = np.asarray(psnr_ref, dtype=float)
    p_test = np.asarray(psnr_test, dtype=float)

    # Need at least 4 points for cubic
    if len(log_ref) < 4 or len(log_test) < 4:
        return float("nan")

    # Fit cubic polynomials log_rate(PSNR)
    poly_ref = np.polyfit(p_ref, log_ref, 3)
    poly_test = np.polyfit(p_test, log_test, 3)

    # Integration interval: overlap of PSNR ranges
    lo = max(p_ref.min(), p_test.min())
    hi = min(p_ref.max(), p_test.max())
    if hi <= lo:
        return float("nan")

    int_ref = np.polyval(np.polyint(poly_ref), hi) - np.polyval(np.polyint(poly_ref), lo)
    int_test = np.polyval(np.polyint(poly_test), hi) - np.polyval(np.polyint(poly_test), lo)
    avg_log_diff = (int_test - int_ref) / (hi - lo)
    return float((np.exp(avg_log_diff) - 1) * 100.0)


def compute_for_channel(df: pd.DataFrame, channel: str) -> list[dict]:
    """channel in {'y', 'u', 'v'}"""
    rows = []
    psnr_col = f"psnr_{channel}_db"
    for (seq, cfg), grp in df.groupby(["sequence", "config"]):
        for test_enc, ref_enc, label in PAIRS:
            t = grp[grp["encoder"] == test_enc].sort_values("qp")
            r = grp[grp["encoder"] == ref_enc].sort_values("qp")
            if len(t) < 4 or len(r) < 4:
                bd = float("nan")
            else:
                bd = bdrate_piecewise_cubic(
                    r["bitrate_kbps"].values, r[psnr_col].values,
                    t["bitrate_kbps"].values, t[psnr_col].values,
                )
            rows.append({
                "sequence": seq, "config": cfg, "comparison": label,
                "channel": channel.upper(), "bdrate_pct": bd,
            })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=str,
                    default=str(RESULTS_DIR / "raw_metrics.csv"))
    ap.add_argument("--output", type=str,
                    default=str(RESULTS_DIR / "bdrate_table.csv"))
    args = ap.parse_args()

    p = Path(args.input)
    if not p.exists():
        print(f"ERROR: {p} not found. Run parse_logs.py first.",
              file=sys.stderr)
        return 1

    df = pd.read_csv(p)
    if df.empty:
        print("ERROR: empty metrics CSV.", file=sys.stderr)
        return 1

    out_rows = []
    for ch in ("y", "u", "v"):
        out_rows.extend(compute_for_channel(df, ch))

    out_df = pd.DataFrame(out_rows)
    # Pivot for readability: rows = (sequence, config, comparison), cols = Y/U/V
    pivot = out_df.pivot_table(
        index=["sequence", "config", "comparison"],
        columns="channel", values="bdrate_pct",
    ).reset_index()
    pivot.to_csv(args.output, index=False, float_format="%.2f")
    print(f"BD-rate written: {args.output}")
    print()
    print(pivot.to_string(index=False))

    # Also dump time-ratio analysis
    time_rows = []
    for (seq, cfg), grp in df.groupby(["sequence", "config"]):
        avg_time = grp.groupby("encoder")["enc_time_sec"].mean().to_dict()
        if "jm" not in avg_time:
            continue
        base = avg_time["jm"]
        if base == 0 or np.isnan(base):
            continue
        for enc in ("jm", "hm", "vtm", "ecm"):
            if enc not in avg_time:
                continue
            time_rows.append({
                "sequence": seq, "config": cfg, "encoder": enc,
                "avg_enc_time_sec": avg_time[enc],
                "ratio_vs_jm": avg_time[enc] / base,
            })
    tr_df = pd.DataFrame(time_rows)
    tr_path = RESULTS_DIR / "time_ratio.csv"
    tr_df.to_csv(tr_path, index=False, float_format="%.3f")
    print(f"\nTime ratio table: {tr_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
