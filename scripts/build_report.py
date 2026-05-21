#!/usr/bin/env python3
"""Generate the final Markdown report plus PNG figures."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "results"
REPORT_DIR = PROJECT_ROOT / "report"
FIG_DIR = REPORT_DIR / "figures"


def main() -> int:
    REPORT_DIR.mkdir(exist_ok=True)
    FIG_DIR.mkdir(exist_ok=True)

    raw_p = RESULTS_DIR / "raw_metrics.csv"
    bd_p = RESULTS_DIR / "bdrate_table.csv"
    tr_p = RESULTS_DIR / "time_ratio.csv"
    if not raw_p.exists():
        print(f"ERROR: missing {raw_p}", file=sys.stderr)
        return 1
    if not bd_p.exists():
        print(f"ERROR: missing {bd_p}. Run compute_bdrate.py first.",
              file=sys.stderr)
        return 1

    raw = pd.read_csv(raw_p)
    bd = pd.read_csv(bd_p)
    tr = pd.read_csv(tr_p) if tr_p.exists() else pd.DataFrame()

    # --- Figure 1: RD curves per (sequence, config) ---
    enc_order = ["jm", "hm", "vtm", "ecm"]
    enc_color = {"jm": "tab:gray", "hm": "tab:blue",
                 "vtm": "tab:green", "ecm": "tab:red"}
    for (seq, cfg), grp in raw.groupby(["sequence", "config"]):
        fig, ax = plt.subplots(figsize=(7, 5))
        for enc in enc_order:
            sub = grp[grp["encoder"] == enc].sort_values("bitrate_kbps")
            if sub.empty:
                continue
            ax.plot(sub["bitrate_kbps"], sub["psnr_y_db"],
                    marker="o", color=enc_color[enc],
                    label=enc.upper())
        ax.set_xscale("log")
        ax.set_xlabel("Bitrate (kbps, log scale)")
        ax.set_ylabel("Y-PSNR (dB)")
        ax.set_title(f"RD curve — {seq} ({cfg})")
        ax.grid(True, which="both", linestyle=":")
        ax.legend()
        fig.tight_layout()
        fig_path = FIG_DIR / f"rd_{seq}_{cfg}.png"
        fig.savefig(fig_path, dpi=140)
        plt.close(fig)

    # --- Figure 2: BD-rate bar chart (Y channel) ---
    bd_y = bd[["sequence", "config", "comparison", "Y"]].copy()
    fig, ax = plt.subplots(figsize=(10, 5))
    labels = [f"{r.sequence}/{r.config}" for r in bd_y.itertuples()]
    comparisons = bd_y["comparison"].unique()
    width = 0.8 / len(comparisons)
    x = range(len(bd_y["sequence"].unique()) * len(bd_y["config"].unique()))
    # Simpler: just plot a table-like summary
    pivot = bd_y.pivot_table(index=["sequence", "config"], columns="comparison",
                             values="Y")
    pivot.plot(kind="bar", ax=ax)
    ax.axhline(0, color="black", linewidth=0.5)
    ax.set_ylabel("BD-rate Y (%) — negative = test saves bits")
    ax.set_title("BD-rate summary (Y channel)")
    ax.grid(True, axis="y", linestyle=":")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "bdrate_summary.png", dpi=140)
    plt.close(fig)

    # --- Figure 3: time ratio vs cumulative BD-rate gain (relative to JM) ---
    if not tr.empty:
        cum = bd[bd["comparison"].isin(["HM-vs-JM", "VTM-vs-JM",
                                         "ECM-vs-JM"])]
        # Use ECM-vs-JM only for cumulative scatter
        scatter_rows = []
        for (seq, cfg), grp in tr.groupby(["sequence", "config"]):
            for _, r in grp.iterrows():
                scatter_rows.append({
                    "encoder": r["encoder"], "sequence": seq, "config": cfg,
                    "time_ratio": r["ratio_vs_jm"],
                })
        sdf = pd.DataFrame(scatter_rows)
        fig, ax = plt.subplots(figsize=(7, 5))
        for enc, sub in sdf.groupby("encoder"):
            ax.scatter([enc] * len(sub), sub["time_ratio"],
                       color=enc_color.get(enc, "k"), s=60, alpha=0.7)
        ax.set_yscale("log")
        ax.set_ylabel("Encoding time ratio vs JM (log)")
        ax.set_title("Encoding time scaling")
        ax.grid(True, which="both", linestyle=":")
        fig.tight_layout()
        fig.savefig(FIG_DIR / "time_scaling.png", dpi=140)
        plt.close(fig)

    # --- Markdown report ---
    md = []
    md.append("# Codec Comparison — Pilot Report\n")
    md.append(f"_Generated from {raw_p.name} ({len(raw)} rows)._\n")

    md.append("## 1. BD-rate (Y channel)\n")
    md.append(bd.to_markdown(index=False, floatfmt=".2f"))
    md.append("\n\n")

    if not tr.empty:
        md.append("## 2. Encoding time ratio (relative to JM)\n")
        md.append(tr.to_markdown(index=False, floatfmt=".2f"))
        md.append("\n\n")

    md.append("## 3. Figures\n")
    for f in sorted(FIG_DIR.glob("*.png")):
        md.append(f"![{f.stem}](figures/{f.name})\n")

    md.append("\n## 4. Raw metrics\n")
    md.append("See `results/raw_metrics.csv` for per-job numbers.\n")

    out_md = REPORT_DIR / "pilot_results.md"
    out_md.write_text("".join(md))
    print(f"Report: {out_md}")
    print(f"Figures: {FIG_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
