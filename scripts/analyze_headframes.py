#!/usr/bin/env python3
"""Head-frames RD analysis: BD-rate and encoding-time saving between two runs.

Extracts per-picture bits / Y-PSNR / ET from ECM (or VTM/HM) head-frames logs,
aggregates each (sequence, QP) into one RD point, and compares a test run
against an anchor run sequence by sequence.

Built for the GeoBlendIntra question: how much coding efficiency does disabling
that tool cost, and how much encoding time does it save, across the five
head-frames sequences. Anchor = `_ctc` (tool on), test = `_nogbi` (tool off).

    python scripts/analyze_headframes.py \
        --anchor-suffix _ctc --test-suffix _nogbi \
        --sequences Campfire,RollerCoaster2,ParkScene,BQMall,BQSquare

Aggregation
-----------
Per (sequence, QP), over the N head pictures:

    bitrate_kbps = sum(bits) / N * fps / 1000
    y_psnr_db    = MSE-domain mean of the per-picture Y-PSNRs
    enc_time_sec = sum(ET)

`fps` is read from the `--FrameRate=` on the log's own `# CMD:` line, so no
per-sequence table can drift out of sync with the runs.

Two averaging modes are reported:

* **plain** — every head picture counts once. This matches
  `scripts/parse_logs.py`, but over-weights the deep temporal layers: the head-7
  set is one picture per TId, whereas a real GOP-32 contains 16 TId-5 pictures
  and only one TId-0.
* **tid-weighted** — each picture is weighted by how often its temporal layer
  occurs in a GOP-32 (TId 0..5 -> 1,1,2,4,8,16 of 32). Closer to what a full
  encode would produce. Follows the `w_top7` idea in the GOP_CTCData reference.

Neither is a CTC-comparable bitrate: the head pictures are a non-contiguous
coding-order diagonal (see README, "Fast mode"). These numbers compare two runs
*of the same picture set* against each other, which is valid; they are not
comparable to a full-sequence encode.

Output
------
`results/<name>_points.csv`   one row per (run, sequence, QP)
`results/<name>_bdrate.csv`   one row per sequence: BD-rate, time saving, overlap
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bd_metrics import bd_rate, mse_mean_psnr, psnr_overlap_pct, time_reduction  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = PROJECT_ROOT / "runs"
RESULTS_DIR = PROJECT_ROOT / "results"

# VTM/ECM per-picture line:
#   POC <n> LId: 0 TId: <t> ( <nalu>, <slice>, QP <q> ) <bits> bits [Y <y> dB ...] [ET <et> ]
# HM omits `LId:` and prints `nQP <q> QP <q>`, so LId and TId are optional here;
# TId defaults to 0 when absent, which disables meaningful --weighting tid.
RE_PIC = re.compile(
    r"^POC\s+(\d+)\s+(?:LId:\s*\d+\s+)?(?:TId:\s*(\d+)\s*)?\([^)]*\)\s+(\d+)\s+bits\s+"
    r"\[Y\s+([\d.]+)\s+dB\s+U\s+([\d.]+)\s+dB\s+V\s+([\d.]+)\s+dB\]"
    r"(?:[^\n]*?\[ET\s+([\d.]+))?",
    re.MULTILINE,
)
RE_FPS = re.compile(r"--FrameRate=([\d.]+)")
RE_QP_IN_NAME = re.compile(r"QP(\d+)")

# Pictures per temporal layer in a GOP-32 random-access hierarchy.
TID_COUNT_IN_GOP32 = {0: 1, 1: 1, 2: 2, 3: 4, 4: 8, 5: 16}

_warnings: list[str] = []


def warn(msg: str) -> None:
    _warnings.append(msg)
    print(f"WARN: {msg}", file=sys.stderr)


# --- parsing ---------------------------------------------------------------
def parse_log(path: Path) -> dict | None:
    """Per-picture records + fps for one encoder log, or None if unusable."""
    text = path.read_text(errors="replace")
    pics = []
    for m in RE_PIC.finditer(text):
        pics.append({
            "poc": int(m.group(1)),
            "tid": int(m.group(2)) if m.group(2) else 0,
            "bits": int(m.group(3)),
            "Y": float(m.group(4)),
            "U": float(m.group(5)),
            "V": float(m.group(6)),
            "et": float(m.group(7)) if m.group(7) else math.nan,
        })
    if not pics:
        warn(f"{path.name}: no per-picture lines — skipped")
        return None
    fps_m = RE_FPS.search(text)
    if not fps_m:
        warn(f"{path.name}: no --FrameRate= on the CMD line — skipped")
        return None
    if any(p["et"] != p["et"] for p in pics):
        warn(f"{path.name}: some pictures have no [ET ...] — time figures partial")
    return {"pics": pics, "fps": float(fps_m.group(1))}


def load_run(run_dir: Path) -> dict[int, dict]:
    """{qp: parsed} for one run directory."""
    logs = sorted((run_dir / "logs").glob("*.log"))
    out: dict[int, dict] = {}
    for f in logs:
        m = RE_QP_IN_NAME.search(f.name)
        if not m:
            warn(f"{f.name}: no QP in filename — skipped")
            continue
        parsed = parse_log(f)
        if parsed:
            out[int(m.group(1))] = parsed
    return out


def load_recon(csv_path: Path, fps_from: dict[int, dict]) -> dict[int, dict]:
    """Load a scripts/estimate_missing_frames.py `*_frames.csv` as a run.

    Used to stand in for an anchor whose encode crashed. Rows flagged
    `estimated` are model output, not measurement — any QP containing one gets
    its encoding time set to NaN, because the estimated pictures borrow their ET
    from the donor run and a time comparison against that donor would be
    circular.
    """
    by_qp: dict[int, dict] = {}
    with csv_path.open() as fh:
        for row in csv.DictReader(fh):
            qp = int(row["qp"])
            e = by_qp.setdefault(qp, {"pics": [], "fps": None, "n_est": 0})
            e["pics"].append({
                "poc": int(row["poc"]), "tid": int(row["tid"]),
                "bits": float(row["bits"]), "Y": float(row["psnr_y_db"]),
                "U": float(row["psnr_u_db"]), "V": float(row["psnr_v_db"]),
                "et": math.nan,
            })
            e["pics"][-1]["estimated"] = (row["source"] == "estimated")
            if row["source"] == "estimated":
                e["n_est"] += 1
    for qp, e in by_qp.items():
        if qp not in fps_from:
            raise ValueError(f"cannot determine fps for QP{qp} from the run logs")
        e["fps"] = fps_from[qp]["fps"]
    return by_qp


def restrict_to_common(a: dict[int, dict], b: dict[int, dict]) -> None:
    """Drop, per QP, any picture that is not *measured* in both runs (in place).

    Estimated pictures count as absent. Otherwise this would be a no-op against
    a reconstructed anchor — the reconstruction carries every POC, so a POC-set
    intersection would keep the very model output the caller is trying to
    exclude.
    """
    for qp in set(a) & set(b):
        sets = []
        for run in (a, b):
            sets.append({p["poc"] for p in run[qp]["pics"]
                         if not p.get("estimated")})
        common = sets[0] & sets[1]
        for run in (a, b):
            run[qp]["pics"] = [p for p in run[qp]["pics"]
                               if p["poc"] in common and not p.get("estimated")]


def identical_points(a: dict, b: dict) -> bool:
    """True if two runs coded a QP to exactly the same bits and PSNR.

    When a tool is switched off but the encoder never chose it, the two
    bitstreams are identical. Such a point is a free control: any difference in
    its measured encoding time is pure machine noise, which calibrates how much
    of a reported time saving is real.
    """
    pa = {p["poc"]: p for p in a["pics"]}
    pb = {p["poc"]: p for p in b["pics"]}
    if set(pa) != set(pb):
        return False
    return all(pa[k]["bits"] == pb[k]["bits"] and pa[k]["Y"] == pb[k]["Y"]
               for k in pa)


# --- aggregation -----------------------------------------------------------
def rd_point(parsed: dict, weighting: str) -> dict:
    """Collapse one log's pictures into a single (bitrate, PSNR, time) point."""
    pics, fps = parsed["pics"], parsed["fps"]
    n = len(pics)

    if weighting == "tid":
        w = [TID_COUNT_IN_GOP32.get(p["tid"], 0) for p in pics]
        if sum(w) == 0:
            raise ValueError("all TId weights are zero")
    else:
        w = [1.0] * n
    tw = sum(w)

    mean_bits = sum(p["bits"] * wi for p, wi in zip(pics, w)) / tw
    # Weighted MSE-domain PSNR mean (MAX cancels; see bd_metrics.mse_mean_psnr).
    inv = sum(wi * 10.0 ** (-p["Y"] / 10.0) for p, wi in zip(pics, w)) / tw
    y_psnr = -10.0 * math.log10(inv)

    ets = [p["et"] for p in pics if p["et"] == p["et"]]
    return {
        "frames": n,
        "bitrate_kbps": mean_bits * fps / 1000.0,
        "y_psnr_db": y_psnr,
        "y_psnr_db_arith": sum(p["Y"] for p in pics) / n,  # parse_logs.py's convention
        "enc_time_sec": sum(ets) if ets else math.nan,
        "total_bits": sum(p["bits"] for p in pics),
        "pocs": sorted(p["poc"] for p in pics),
    }


def curve(run: dict[int, dict], qps: list[int], weighting: str) -> dict:
    """Assemble the RD curve for one sequence across QPs."""
    pts = {qp: rd_point(run[qp], weighting) for qp in qps}
    return {
        "qps": qps,
        "rate": [pts[q]["bitrate_kbps"] for q in qps],
        "psnr": [pts[q]["y_psnr_db"] for q in qps],
        "time": sum(pts[q]["enc_time_sec"] for q in qps),
        "points": pts,
    }


# --- main ------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(
        description="BD-rate and time saving between two head-frames runs.")
    ap.add_argument("--runs-dir", type=Path, default=RUNS_DIR)
    ap.add_argument("--anchor-suffix", default="_ctc",
                    help="run-dir suffix of the anchor/reference (default: _ctc)")
    ap.add_argument("--test-suffix", default="_nogbi",
                    help="run-dir suffix of the run under test (default: _nogbi)")
    ap.add_argument("--prefix", default="fastTop7_",
                    help="run-dir prefix (default: fastTop7_)")
    ap.add_argument("--sequences", required=True,
                    help="comma-separated sequence names")
    ap.add_argument("--weighting", choices=["plain", "tid", "both"], default="both",
                    help="picture weighting for the aggregate (default: both)")
    ap.add_argument("--name", default="headframes_gbi",
                    help="stem for the output CSVs")
    ap.add_argument("--out-dir", type=Path, default=RESULTS_DIR)
    ap.add_argument("--anchor-recon", action="append", default=[], metavar="SEQ=CSV",
                    help="replace a sequence's anchor with a reconstruction CSV "
                         "from estimate_missing_frames.py (repeatable). The "
                         "result is model-assisted, not measured — see --help "
                         "notes and the printed caveat.")
    ap.add_argument("--common-subset", action="store_true",
                    help="restrict both runs, per QP, to the pictures they share. "
                         "Fully measured, but the curve then rests on fewer "
                         "pictures than the other sequences.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    seqs = [s.strip() for s in args.sequences.split(",") if s.strip()]
    modes = ["plain", "tid"] if args.weighting == "both" else [args.weighting]
    recon_map: dict[str, Path] = {}
    for spec in args.anchor_recon:
        if "=" not in spec:
            sys.exit(f"ERROR: --anchor-recon expects SEQ=CSV, got '{spec}'")
        s, p = spec.split("=", 1)
        recon_map[s.strip()] = Path(p)

    point_rows: list[dict] = []
    result_rows: list[dict] = []
    control_rows: list[dict] = []

    for seq in seqs:
        a_dir = args.runs_dir / f"{args.prefix}{seq}{args.anchor_suffix}"
        b_dir = args.runs_dir / f"{args.prefix}{seq}{args.test_suffix}"
        if not a_dir.is_dir() or not b_dir.is_dir():
            warn(f"{seq}: missing {a_dir.name if not a_dir.is_dir() else b_dir.name} "
                 f"— sequence skipped")
            continue

        a_run, b_run = load_run(a_dir), load_run(b_dir)
        seq_note = ""
        if seq in recon_map:
            try:
                a_run = load_recon(recon_map[seq], a_run)
            except (OSError, ValueError, KeyError) as e:
                warn(f"{seq}: could not load reconstruction {recon_map[seq]} ({e})")
                continue
            n_est = sum(v["n_est"] for v in a_run.values())
            seq_note = f"anchor reconstructed ({n_est} est. pictures)"
            warn(f"{seq}: anchor taken from {Path(recon_map[seq]).name} with "
                 f"{n_est} estimated picture(s). Those were derived FROM the test "
                 f"run, so this BD-rate is biased toward 0 by construction — "
                 f"cross-check it against --common-subset before quoting.")
        if args.common_subset:
            restrict_to_common(a_run, b_run)
            seq_note = (seq_note + "; " if seq_note else "") + "common subset only"
        qps = sorted(set(a_run) & set(b_run))
        if len(qps) < 3:
            warn(f"{seq}: only {len(qps)} shared QP(s) {qps}; BD-rate needs >=3 "
                 f"— sequence skipped")
            continue
        if set(a_run) != set(b_run):
            warn(f"{seq}: QP sets differ (anchor {sorted(a_run)}, test "
                 f"{sorted(b_run)}); using the intersection {qps}")
            pic_note_extra = "QP SUBSET"
        else:
            pic_note_extra = ""
        if pic_note_extra:
            seq_note = (seq_note + "; " if seq_note else "") + pic_note_extra

        # Control points: QPs the two runs coded identically. Their ET delta is
        # pure timing noise and bounds how much of any time saving is real.
        for qp in qps:
            if identical_points(a_run[qp], b_run[qp]):
                ta = sum(p["et"] for p in a_run[qp]["pics"] if p["et"] == p["et"])
                tb = sum(p["et"] for p in b_run[qp]["pics"] if p["et"] == p["et"])
                if ta > 0:
                    control_rows.append({
                        "sequence": seq, "qp": qp,
                        "anchor_time_sec": round(ta, 1),
                        "test_time_sec": round(tb, 1),
                        "apparent_saving_pct": round((ta - tb) / ta * 100.0, 3),
                    })

        # A curve is only meaningful if both runs cover the same pictures.
        pic_note = seq_note
        for qp in qps:
            pa = sorted(p["poc"] for p in a_run[qp]["pics"])
            pb = sorted(p["poc"] for p in b_run[qp]["pics"])
            if pa != pb:
                if "MISMATCH" not in pic_note:
                    pic_note = (pic_note + "; " if pic_note else "") + \
                               "PICTURE-SET MISMATCH"
                warn(f"{seq} QP{qp}: anchor has {len(pa)} pictures {pa}, test has "
                     f"{len(pb)} {pb}. The two points are NOT comparable — BD-rate "
                     f"for this sequence is invalid until the gap is closed "
                     f"(reconstruct the anchor, or drop to the common subset).")

        for mode in modes:
            ca = curve(a_run, qps, mode)
            cb = curve(b_run, qps, mode)

            for tag, c in ((args.anchor_suffix.lstrip("_") or "anchor", ca),
                           (args.test_suffix.lstrip("_") or "test", cb)):
                for qp in qps:
                    p = c["points"][qp]
                    point_rows.append({
                        "sequence": seq, "run": tag, "weighting": mode, "qp": qp,
                        "frames": p["frames"],
                        "bitrate_kbps": round(p["bitrate_kbps"], 3),
                        "y_psnr_db_mse_mean": round(p["y_psnr_db"], 5),
                        "y_psnr_db_arith_mean": round(p["y_psnr_db_arith"], 5),
                        "enc_time_sec": ("" if p["enc_time_sec"] != p["enc_time_sec"]
                                         else round(p["enc_time_sec"], 3)),
                        "total_bits": p["total_bits"],
                    })

            try:
                bd = bd_rate(ca["rate"], ca["psnr"], cb["rate"], cb["psnr"])
                ov = psnr_overlap_pct(ca["psnr"], cb["psnr"])
            except ValueError as e:
                warn(f"{seq} [{mode}]: BD-rate failed ({e})")
                continue
            # An anchor with no usable ET (e.g. a reconstruction, whose estimated
            # pictures borrow the donor's time) cannot yield a time saving.
            if ca["time"] != ca["time"] or ca["time"] <= 0:
                ts = math.nan
            else:
                ts = time_reduction(ca["time"], cb["time"])
            result_rows.append({
                "sequence": seq, "weighting": mode, "qps": "/".join(map(str, qps)),
                "bdrate_y_pct": round(bd, 4),
                "time_saving_pct": "" if ts != ts else round(ts, 3),
                "psnr_overlap_pct": round(ov, 2),
                "anchor_time_sec": "" if ca["time"] != ca["time"] else round(ca["time"], 1),
                "test_time_sec": round(cb["time"], 1),
                "note": pic_note,
            })

    if not result_rows:
        print("Nothing computed.", file=sys.stderr)
        return 1

    anchor_name = args.anchor_suffix.lstrip("_") or "anchor"
    test_name = args.test_suffix.lstrip("_") or "test"
    print(f"BD-rate of '{test_name}' relative to anchor '{anchor_name}' "
          f"(negative = test needs fewer bits)")
    print(f"Time saving of '{test_name}' vs '{anchor_name}' "
          f"(positive = test is faster)\n")

    for mode in modes:
        rows = [r for r in result_rows if r["weighting"] == mode]
        if not rows:
            continue
        label = ("plain mean over head pictures" if mode == "plain"
                 else "weighted by TId frequency in GOP-32")
        print(f"--- weighting: {mode}  ({label}) ---")
        print(f"  {'sequence':<16} {'BD-rate Y %':>12} {'time saving %':>14} "
              f"{'overlap %':>10}  note")
        for r in rows:
            ts = f"{r['time_saving_pct']:>14.2f}" if r["time_saving_pct"] != "" \
                 else f"{'n/a':>14}"
            print(f"  {r['sequence']:<16} {r['bdrate_y_pct']:>12.4f} "
                  f"{ts} {r['psnr_overlap_pct']:>10.1f}  {r['note']}")
        clean = [r for r in rows if not r["note"]]
        if clean:
            bd_vals = [r["bdrate_y_pct"] for r in clean]
            ts_vals = [r["time_saving_pct"] for r in clean
                       if r["time_saving_pct"] != ""]
            print(f"  {'mean':<16} {sum(bd_vals)/len(bd_vals):>12.4f} "
                  f"{(sum(ts_vals)/len(ts_vals) if ts_vals else float('nan')):>14.2f}"
                  f"   <- fully measured sequences only, n={len(clean)}")
        if len(clean) < len(rows):
            print(f"  ({len(rows) - len(clean)} sequence(s) excluded from the mean; "
                  f"see the note column)")
        print()

    low_ov = [r for r in result_rows if r["psnr_overlap_pct"] < 75.0]
    if low_ov:
        warn(f"{len(low_ov)} sequence/mode pair(s) have PSNR overlap < 75 % — "
             f"BD-rate there is partly extrapolated (see HANDOFF 6.9)")

    # --- noise floor from the control points ------------------------------
    if control_rows:
        floor = max(abs(r["apparent_saving_pct"]) for r in control_rows)
        print("--- timing control points (runs coded BIT-IDENTICALLY) ---")
        print("  At these QPs the tool was never selected, so the two encodes "
              "produced the same\n  bitstream. Any apparent time difference is "
              "machine noise, not the tool.")
        print(f"  {'sequence':<16} {'QP':>4} {'anchor s':>10} {'test s':>10} "
              f"{'apparent saving %':>18}")
        for r in control_rows:
            print(f"  {r['sequence']:<16} {r['qp']:>4} {r['anchor_time_sec']:>10.1f} "
                  f"{r['test_time_sec']:>10.1f} {r['apparent_saving_pct']:>18.2f}")
        print(f"\n  => TIMING NOISE FLOOR: +/-{floor:.2f} % "
              f"(worst control point, n={len(control_rows)})")
        suspect = [r for r in result_rows
                   if r["time_saving_pct"] != ""
                   and abs(r["time_saving_pct"]) < floor]
        if suspect:
            names = sorted({r["sequence"] for r in suspect})
            print(f"  Time savings below that are indistinguishable from noise: "
                  f"{', '.join(names)}.")
        print("  Do not quote a mean time saving without stating this floor.")
        tied = {}
        for r in control_rows:
            tied.setdefault(r["sequence"], []).append(r["qp"])
        print(f"\n  The same points are exact ties in rate AND quality, so they "
              f"contribute nothing to\n  BD-rate either: "
              + "; ".join(f"{s} QP{'/QP'.join(map(str, q))}"
                          for s, q in sorted(tied.items()))
              + ".\n  Those curves effectively rest on the remaining QPs, with one "
                "endpoint pinned.\n")
    else:
        print("--- no bit-identical control points found; the timing noise floor "
              "is unmeasured ---\n")

    if args.dry_run:
        print("--dry-run: no files written.")
        return 0

    args.out_dir.mkdir(parents=True, exist_ok=True)
    f_pts = args.out_dir / f"{args.name}_points.csv"
    f_bd = args.out_dir / f"{args.name}_bdrate.csv"
    with f_pts.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(point_rows[0].keys()))
        w.writeheader()
        w.writerows(point_rows)
    with f_bd.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(result_rows[0].keys()))
        w.writeheader()
        w.writerows(result_rows)
    print(f"Wrote {f_pts.relative_to(PROJECT_ROOT)}")
    print(f"Wrote {f_bd.relative_to(PROJECT_ROOT)}")
    if control_rows:
        f_ctl = args.out_dir / f"{args.name}_controls.csv"
        with f_ctl.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(control_rows[0].keys()))
            w.writeheader()
            w.writerows(control_rows)
        print(f"Wrote {f_ctl.relative_to(PROJECT_ROOT)}")
    if _warnings:
        print(f"\n{len(_warnings)} warning(s) were raised — read them before "
              f"quoting these numbers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
