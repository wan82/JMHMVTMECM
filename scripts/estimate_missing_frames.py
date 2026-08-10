#!/usr/bin/env python3
"""Reconstruct an *estimated* tool-on curve for QP points whose tool-on encode
crashed partway through.

Background
----------
ECM-18.0 has a `GeoBlendIntra` defect (see HANDOFF.md 6.11) that aborts the
encoder mid-sequence on some (sequence, QP) combinations. For Campfire the
head-frames RA run lost QP27 and QP32 — both died on the 5th coded picture
(POC 4), so pictures POC 4/2/1 are missing at those two QPs. A full re-run with
`--GeoBlendIntra=0` completes all four QPs, but that curve is *tool-off* and so
is not directly comparable with the tool-on points of other sequences.

This script splices the two: every picture the tool-on run actually produced is
kept **as measured**, and only the missing pictures are filled in from the
tool-off ("donor") run, corrected by the tool's measured effect.

Method
------
For picture POC ``p`` at a QP ``q`` where the tool-on run crashed:

    bits_est(p,q) = bits_off(p,q) * R(p,q)
    psnr_est(p,q) = psnr_off(p,q) + D(p,q)

``R`` (bit ratio) and ``D`` (PSNR delta, dB) are the tool's effect on that
*same picture*, linearly interpolated in QP between the two anchor QPs that
bracket ``q`` (anchors = QPs where the tool-on run completed). Interpolating
per-POC rather than per-QP matters: the effect is strongly picture-dependent
(I-slices are bit-exact, since GeoBlendIntra is an inter tool) and only weakly
QP-dependent.

Validation, and its limits
--------------------------
The method is checked against held-out ground truth: POCs that the crashed run
*did* code are predicted using only the anchor QPs, then compared with their
measured values.

Read that error bar with care. The held-out pictures are the ones coded *before*
the crash — i.e. the shallow temporal layers — while the pictures actually being
filled are the ones after it, in deeper layers where the tool's effect is
larger. The script therefore also reports the tool's measured effect at the
anchors *restricted to the TIds being filled*, which is the more honest
uncertainty scale. Both numbers are printed; the larger one is the one to quote.

Output
------
CSVs under ``results/`` plus a stdout report. Every per-picture row carries a
``source`` column (``measured`` / ``estimated``); every summary row carries an
``is_reconstructed`` flag and a ``frames_estimated`` count.

**Estimated points are never written into ``results/raw_metrics.csv``.** They
are a stopgap for keeping a curve usable, not measured data; anything published
from them must say so. See README "Reconstructing a crashed QP point".

Usage
-----
    python scripts/estimate_missing_frames.py \
        --on-run  runs/fastTop7_Campfire_ctc \
        --off-run runs/fastTop7_Campfire_nogbi \
        --label   Campfire_RA_head7_recon

    # print the report and validation table, write nothing
    python scripts/estimate_missing_frames.py ... --dry-run
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "results"

# Per-picture line emitted by HM/VTM/ECM, e.g.
#   POC    4 LId:  0 TId: 3 ( RASL, B-SLICE, QP 43 )   130536 bits [Y 35.8780 dB ...
RE_PERFRAME = re.compile(
    r"^POC\s+(\d+)\s+LId:\s*\d+\s+TId:\s*(\d+)\s*\(\s*([^,]+),\s*([^,]+),\s*QP\s*(\d+)\s*\)"
    r"\s+(\d+)\s+bits\s+"
    r"\[Y\s+([\d.]+)\s+dB\s+U\s+([\d.]+)\s+dB\s+V\s+([\d.]+)\s+dB\]"
    r"(?:[^\n]*?\[ET\s+([\d.]+))?",
    re.MULTILINE,
)
RE_QP_IN_NAME = re.compile(r"QP(\d+)")
RE_CMD_FRAMERATE = re.compile(r"--FrameRate=([\d.]+)")
RE_GEOBLEND = re.compile(r"GeoBlendIntra:(\d)")
RE_CTU = re.compile(r"ECM ENC CFG: CTU:(\d+)")

CHANNELS = ("Y", "U", "V")

_warnings: list[str] = []


def warn(msg: str) -> None:
    """Collect a warning so it can be repeated at the end of the report; a
    warning buried above a clean-looking table gets missed."""
    _warnings.append(msg)
    print(f"WARN: {msg}", file=sys.stderr)


# --- parsing ---------------------------------------------------------------
def parse_log(path: Path) -> dict:
    """Return per-picture data plus run metadata for one encoder log."""
    text = path.read_text(errors="replace")
    pics: dict[int, dict] = {}
    for m in RE_PERFRAME.finditer(text):
        poc = int(m.group(1))
        if poc in pics:
            warn(f"{path.name}: duplicate line for POC {poc}; keeping the last")
        pics[poc] = {
            "tid": int(m.group(2)),
            "nalu": m.group(3).strip(),
            "slice": m.group(4).strip(),
            "slice_qp": int(m.group(5)),
            "bits": int(m.group(6)),
            "Y": float(m.group(7)),
            "U": float(m.group(8)),
            "V": float(m.group(9)),
            "et": float(m.group(10)) if m.group(10) else math.nan,
        }
    fps_m = RE_CMD_FRAMERATE.search(text)
    if not fps_m:
        warn(f"{path.name}: no --FrameRate= on the CMD line; bitrate will be NaN")
    gb_m = RE_GEOBLEND.search(text)
    ctu_m = RE_CTU.search(text)
    return {
        "pics": pics,
        "fps": float(fps_m.group(1)) if fps_m else math.nan,
        "geoblend": int(gb_m.group(1)) if gb_m else None,
        "ctu": int(ctu_m.group(1)) if ctu_m else None,
        "path": path,
    }


def load_run(run_dir: Path, role: str) -> dict[int, dict]:
    """Return {qp: parsed_log} for every *.log in run_dir/logs."""
    logs = sorted((run_dir / "logs").glob("*.log"))
    if not logs:
        sys.exit(f"ERROR: no logs found under {run_dir / 'logs'}")
    out: dict[int, dict] = {}
    for f in logs:
        m = RE_QP_IN_NAME.search(f.name)
        if not m:
            warn(f"{role}: skipping {f.name} (no QP in filename)")
            continue
        parsed = parse_log(f)
        if not parsed["pics"]:
            warn(f"{role}: {f.name} has no per-picture lines — that QP point is "
                 f"dropped from the curve entirely")
            continue
        out[int(m.group(1))] = parsed
    return out


# --- the correction model --------------------------------------------------
def bracketing_anchors(anchors: list[int], qp: int) -> tuple[int, int, bool]:
    """Two anchors closest around `qp`. Returns (lo, hi, in_range).

    Using the bracketing pair rather than the global endpoints matters as soon
    as there are three or more anchors: the nearest anchors carry the most
    information about the target QP.
    """
    below = [a for a in anchors if a <= qp]
    above = [a for a in anchors if a >= qp]
    if below and above:
        return max(below), min(above), True
    # Target sits outside the anchor range: extrapolation. Use the two anchors
    # nearest to it and let the caller flag it.
    ordered = sorted(anchors, key=lambda a: abs(a - qp))[:2]
    return min(ordered), max(ordered), False


def interp(x: float, x0: float, y0: float, x1: float, y1: float) -> float:
    """Linear interpolation in x. Extrapolates if x is outside [x0, x1]; callers
    must flag that case (see bracketing_anchors)."""
    if x1 == x0:
        return y0
    return y0 + (x - x0) / (x1 - x0) * (y1 - y0)


def tool_effect(on: dict, off: dict, poc: int, anchors: list[int]) -> dict | None:
    """Measured tool effect on picture `poc` at each anchor QP, or None if the
    picture is not present in both runs at every anchor."""
    eff = {}
    for q in anchors:
        if q not in on or q not in off:
            return None
        pon, poff = on[q]["pics"].get(poc), off[q]["pics"].get(poc)
        if pon is None or poff is None or poff["bits"] == 0:
            return None
        eff[q] = {
            "R": pon["bits"] / poff["bits"],
            **{f"D{c}": pon[c] - poff[c] for c in CHANNELS},
        }
    return eff


def predict(off_pic: dict, eff: dict, anchors: list[int], qp: int) -> dict:
    """Apply the QP-interpolated tool effect to a donor picture."""
    lo, hi, _ = bracketing_anchors(anchors, qp)
    r = interp(qp, lo, eff[lo]["R"], hi, eff[hi]["R"])
    out = {"bits": off_pic["bits"] * r, "_R": r}
    for c in CHANNELS:
        d = interp(qp, lo, eff[lo][f"D{c}"], hi, eff[hi][f"D{c}"])
        out[c] = off_pic[c] + d
        out[f"_D{c}"] = d
    return out


def aggregate(pics: list[dict], fps: float) -> dict:
    """Match parse_logs.py's head-frames convention: mean PSNR over pictures,
    bitrate = mean bits/picture * picture rate."""
    n = len(pics)
    if n == 0:
        return {"frames_encoded": 0, "bitrate_kbps": math.nan, "total_bits": 0,
                **{f"psnr_{c.lower()}_db": math.nan for c in CHANNELS}}
    total_bits = sum(p["bits"] for p in pics)
    out = {
        "frames_encoded": n,
        "bitrate_kbps": (total_bits / n) * fps / 1000.0 if fps == fps else math.nan,
        "total_bits": total_bits,
    }
    for c in CHANNELS:
        out[f"psnr_{c.lower()}_db"] = sum(p[c] for p in pics) / n
    return out


# --- validation ------------------------------------------------------------
def validate(on: dict, off: dict, anchors: list[int], targets: list[int],
             ref_pocs: list[int]) -> list[dict]:
    """Held-out check: for every picture the crashed runs DID code, predict it
    from the anchors alone and compare against the measured value.

    Also scores the trivial baseline of using the donor picture uncorrected. If
    the corrected model is not clearly better, the tool's effect is below the
    encoder's own RD jitter and the correction is cosmetic.
    """
    rows = []
    for qp in targets:
        if qp not in off:
            continue
        for poc in ref_pocs:
            if poc not in on[qp]["pics"] or poc not in off[qp]["pics"]:
                continue
            eff = tool_effect(on, off, poc, anchors)
            if eff is None:
                continue
            donor = off[qp]["pics"][poc]
            pred = predict(donor, eff, anchors, qp)
            truth = on[qp]["pics"][poc]
            row = {
                "qp": qp,
                "poc": poc,
                "tid": truth["tid"],
                "trivial": int(truth["bits"] == donor["bits"]
                               and truth["Y"] == donor["Y"]),
                "bits_true": truth["bits"],
                "bits_pred": pred["bits"],
                "bits_err_pct": 100.0 * (pred["bits"] - truth["bits"]) / truth["bits"],
                "bits_err_pct_donor_only":
                    100.0 * (donor["bits"] - truth["bits"]) / truth["bits"],
            }
            for c in CHANNELS:
                row[f"psnr_{c.lower()}_err_db"] = pred[c] - truth[c]
            row["psnr_y_err_db_donor_only"] = donor["Y"] - truth["Y"]
            rows.append(row)
    return rows


def anchor_effect_by_tid(on: dict, off: dict, anchors: list[int],
                         tids: set[int]) -> dict:
    """Largest measured tool effect at the anchor QPs, restricted to the given
    temporal layers. This is the uncertainty scale that actually applies to the
    filled-in pictures, which the held-out validation cannot reach."""
    worst = {"bits_pct": 0.0, "Y_db": 0.0, "at": None}
    for q in anchors:
        if q not in off:
            continue
        for poc, pon in on[q]["pics"].items():
            if pon["tid"] not in tids:
                continue
            poff = off[q]["pics"].get(poc)
            if poff is None or poff["bits"] == 0:
                continue
            db = abs(100.0 * (pon["bits"] - poff["bits"]) / poff["bits"])
            dy = abs(pon["Y"] - poff["Y"])
            if db > worst["bits_pct"] or dy > worst["Y_db"]:
                if db > worst["bits_pct"]:
                    worst["bits_pct"] = db
                    worst["at"] = (q, poc, pon["tid"])
                worst["Y_db"] = max(worst["Y_db"], dy)
    return worst


# --- main ------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Reconstruct estimated tool-on data for crashed QP points.")
    ap.add_argument("--on-run", required=True, type=Path,
                    help="run dir of the tool-on (GeoBlendIntra=1) encode, may be partial")
    ap.add_argument("--off-run", required=True, type=Path,
                    help="run dir of the complete tool-off (--GeoBlendIntra=0) donor encode")
    ap.add_argument("--label", default="reconstructed",
                    help="name stem for the output CSVs")
    ap.add_argument("--out-dir", type=Path, default=RESULTS_DIR)
    ap.add_argument("--dry-run", action="store_true", help="print only, write nothing")
    args = ap.parse_args()

    on = load_run(args.on_run, "on-run")
    off = load_run(args.off_run, "off-run")

    # Sanity: the two runs must differ only in the tool, not in CTU size.
    for qp in sorted(set(on) & set(off)):
        if on[qp]["ctu"] != off[qp]["ctu"]:
            sys.exit(f"ERROR: CTU mismatch at QP{qp}: on={on[qp]['ctu']} "
                     f"off={off[qp]['ctu']}. The runs are not comparable.")
    if {on[q]["geoblend"] for q in on} == {off[q]["geoblend"] for q in off}:
        warn("both runs report the same GeoBlendIntra setting; expected the donor "
             "to be tool-off. Check you passed the right directories.")
    for qp in sorted(set(off) - set(on)):
        warn(f"QP{qp} exists in the donor but not the tool-on run — it is not part "
             f"of this curve and is ignored")
    for qp in sorted(set(on) - set(off)):
        warn(f"QP{qp} has no donor log; its missing pictures cannot be filled")

    # Reference picture set = union over BOTH runs, in donor coding order where
    # possible. Deriving it from the donor alone would silently drop any picture
    # the tool-on run measured but the donor never coded.
    ref_pocs: list[int] = []
    for src in (off, on):
        for qp in sorted(src):
            for poc in src[qp]["pics"]:
                if poc not in ref_pocs:
                    ref_pocs.append(poc)

    # An anchor is a QP whose tool-on run covers the FULL reference set — not
    # merely "covers whatever the donor happened to have".
    anchors = sorted(q for q in on if set(ref_pocs) <= set(on[q]["pics"]))
    targets = sorted(q for q in on if q not in anchors)
    if len(anchors) < 2:
        sys.exit(f"ERROR: need >=2 tool-on QPs covering all {len(ref_pocs)} reference "
                 f"pictures to use as anchors; found {anchors}")
    if not targets:
        print("Nothing to reconstruct: every tool-on QP is complete.")
        return 0

    print(f"Anchors (complete tool-on): QP{', QP'.join(map(str, anchors))}")
    print(f"Targets  (crashed, to fill): QP{', QP'.join(map(str, targets))}")
    print(f"Reference picture set ({len(ref_pocs)}, coding order): {ref_pocs}")

    for q in targets:
        lo, hi, in_range = bracketing_anchors(anchors, q)
        if not in_range:
            warn(f"QP{q} lies OUTSIDE the anchor range [{min(anchors)}, "
                 f"{max(anchors)}] — the correction is EXTRAPOLATED from QP{lo}/"
                 f"QP{hi}, which amplifies noise rather than reducing it. Treat "
                 f"this point as unvalidated.")
        ignored = [a for a in anchors if a not in (lo, hi)]
        if ignored:
            print(f"  QP{q}: interpolating between QP{lo} and QP{hi} "
                  f"(anchors {ignored} not adjacent, unused)")

    # Anchors where the tool changed nothing carry no information.
    dead = [q for q in anchors
            if q in off and all(
                on[q]["pics"][p]["bits"] == off[q]["pics"].get(p, {}).get("bits")
                and on[q]["pics"][p]["Y"] == off[q]["pics"].get(p, {}).get("Y")
                for p in on[q]["pics"] if p in off[q]["pics"])]
    if dead:
        warn(f"anchor QP{'/QP'.join(map(str, dead))}: tool-on and tool-off are "
             f"identical, so this anchor contributes zero information. The "
             f"correction is effectively a scaled single-anchor extrapolation, "
             f"not a two-point interpolation.")
    print()

    # --- validation first: earn the right to trust the numbers below --------
    vrows = validate(on, off, anchors, targets, ref_pocs)
    print("Validation — pictures the crashed runs DID code, predicted from anchors only:")
    print(f"  {'QP':>3} {'POC':>4} {'TId':>3} {'bits true':>10} {'bits pred':>11} "
          f"{'err %':>8} {'(donor)':>8} {'dY':>9} {'dU':>9} {'dV':>9}")
    for r in vrows:
        note = "  (identical, no information)" if r["trivial"] else ""
        print(f"  {r['qp']:>3} {r['poc']:>4} {r['tid']:>3} {r['bits_true']:>10} "
              f"{r['bits_pred']:>11.1f} {r['bits_err_pct']:>+8.4f} "
              f"{r['bits_err_pct_donor_only']:>+8.4f} "
              f"{r['psnr_y_err_db']:>+9.5f} {r['psnr_u_err_db']:>+9.5f} "
              f"{r['psnr_v_err_db']:>+9.5f}{note}")

    informative = [r for r in vrows if not r["trivial"]]
    if informative:
        mab = max(abs(r["bits_err_pct"]) for r in informative)
        may = max(abs(r["psnr_y_err_db"]) for r in informative)
        nab = max(abs(r["bits_err_pct_donor_only"]) for r in informative)
        nay = max(abs(r["psnr_y_err_db_donor_only"]) for r in informative)
        print(f"  -> corrected : worst |bitrate err| {mab:.4f} %, "
              f"|Y-PSNR err| {may:.5f} dB")
        print(f"  -> donor only: worst |bitrate err| {nab:.4f} %, "
              f"|Y-PSNR err| {nay:.5f} dB")
        print(f"  -> n = {len(informative)} informative of {len(vrows)} held-out "
              f"pictures ({len(vrows) - len(informative)} are bit-identical "
              f"I-slices and prove nothing)")
        if mab >= nab * 0.9:
            print("  -> NOTE: the correction does not beat using the donor "
                  "uncorrected. On these pictures the\n     tool moves less than "
                  "the encoder's own RD jitter, so a filled-in value is honestly "
                  "just\n     'the tool-off encode of that picture'.")
    else:
        print("  (no informative held-out pictures — the output is UNVALIDATED)")
    print()

    # --- the error bar that actually applies to the filled pictures ---------
    filled_tids = {off[q]["pics"][p]["tid"]
                   for q in targets if q in off
                   for p in ref_pocs
                   if p not in on[q]["pics"] and p in off[q]["pics"]}
    validated_tids = {r["tid"] for r in informative}
    if filled_tids and not (filled_tids <= validated_tids):
        w = anchor_effect_by_tid(on, off, anchors, filled_tids)
        print(f"Scope of the validation: held-out pictures are TId "
              f"{sorted(validated_tids) or '-'}, but the pictures being FILLED are "
              f"TId {sorted(filled_tids)}.")
        print(f"  Those layers are not represented above. At the anchor QPs the "
              f"tool's measured effect on\n  TId {sorted(filled_tids)} reaches "
              f"{w['bits_pct']:.4f} % in bits and {w['Y_db']:.5f} dB in Y-PSNR"
              + (f" (worst at QP{w['at'][0]} POC{w['at'][1]})" if w["at"] else "")
              + ".")
        print("  Quote THAT as the uncertainty on the reconstructed pictures, not "
              "the held-out figure.")
        print()

    # --- reconstruct --------------------------------------------------------
    frame_rows: list[dict] = []
    summary_rows: list[dict] = []
    unfillable: list[tuple[int, int]] = []

    for qp in sorted(on):
        fps = on[qp]["fps"]
        pics_out = []
        n_est = 0
        for poc in ref_pocs:
            measured = on[qp]["pics"].get(poc)
            if measured is not None:
                rec = {c: measured[c] for c in CHANNELS}
                rec.update(bits=float(measured["bits"]), tid=measured["tid"],
                           slice=measured["slice"], et=measured["et"],
                           source="measured", R=math.nan)
            else:
                donor = off.get(qp, {}).get("pics", {}).get(poc)
                eff = tool_effect(on, off, poc, anchors)
                if donor is None or eff is None:
                    unfillable.append((qp, poc))
                    continue
                pred = predict(donor, eff, anchors, qp)
                rec = {c: pred[c] for c in CHANNELS}
                rec.update(bits=pred["bits"], tid=donor["tid"], slice=donor["slice"],
                           et=donor["et"], source="estimated", R=pred["_R"])
                n_est += 1
            rec.update(qp=qp, poc=poc)
            pics_out.append(rec)
            frame_rows.append({
                "label": args.label, "qp": qp, "poc": poc, "tid": rec["tid"],
                "slice_type": rec["slice"], "source": rec["source"],
                "bits": round(rec["bits"], 1),
                "psnr_y_db": round(rec["Y"], 5),
                "psnr_u_db": round(rec["U"], 5),
                "psnr_v_db": round(rec["V"], 5),
                "bit_ratio_applied": "" if rec["R"] != rec["R"] else round(rec["R"], 6),
                # ET of whichever run this row came from (tool-on for measured,
                # donor for estimated) — mixed provenance, never a complexity
                # measurement for the spliced curve. See enc_time_sec below.
                "et_sec_of_source_run": "" if rec["et"] != rec["et"] else round(rec["et"], 3),
            })

        agg = aggregate(pics_out, fps)
        summary_rows.append({
            "label": args.label,
            "encoder": "ecm",
            "qp": qp,
            "frames": agg["frames_encoded"],
            "frames_estimated": n_est,
            "is_reconstructed": int(n_est > 0),
            "bitrate_kbps": round(agg["bitrate_kbps"], 2),
            "psnr_y_db": round(agg["psnr_y_db"], 4),
            "psnr_u_db": round(agg["psnr_u_db"], 4),
            "psnr_v_db": round(agg["psnr_v_db"], 4),
            # Deliberately omitted: encoding time. A spliced curve mixes two
            # different tool configs, so its wall-clock is not a valid
            # complexity measurement (HANDOFF 6.3 / 7.3).
            "enc_time_sec": "",
        })

    if unfillable:
        warn(f"{len(unfillable)} picture(s) could not be filled (no donor or no "
             f"anchor effect): {unfillable}")

    # A curve whose points rest on different picture sets is not a curve.
    counts = {r["frames"] for r in summary_rows}
    if len(counts) > 1:
        warn(f"picture counts differ across QPs {sorted(counts)} — these points "
             f"are NOT comparable and must not be fed to BD-rate. Fix the gaps "
             f"first.")
    nan_qps = [r["qp"] for r in summary_rows if r["bitrate_kbps"] != r["bitrate_kbps"]]
    if nan_qps:
        warn(f"bitrate is NaN for QP{nan_qps} (missing --FrameRate=)")

    print("Reconstructed summary (head-frames convention: mean PSNR, "
          "mean bits/pic x fps):")
    print(f"  {'QP':>3} {'frames':>6} {'est':>4} {'kbps':>10} {'Y dB':>8} "
          f"{'U dB':>8} {'V dB':>8}")
    for r in summary_rows:
        flag = "*" if r["is_reconstructed"] else " "
        print(f"  {r['qp']:>3} {r['frames']:>6} {r['frames_estimated']:>4} "
              f"{r['bitrate_kbps']:>10.2f} {r['psnr_y_db']:>8.4f} "
              f"{r['psnr_u_db']:>8.4f} {r['psnr_v_db']:>8.4f} {flag}")
    print("  * = contains estimated pictures")
    print()

    if args.dry_run:
        if _warnings:
            print(f"{len(_warnings)} warning(s) above — re-read them before using "
                  f"these numbers.")
        print("--dry-run: no files written.")
        return 0

    args.out_dir.mkdir(parents=True, exist_ok=True)
    f_frames = args.out_dir / f"{args.label}_frames.csv"
    f_summary = args.out_dir / f"{args.label}_summary.csv"
    f_valid = args.out_dir / f"{args.label}_validation.csv"

    with f_frames.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(frame_rows[0].keys()))
        w.writeheader()
        w.writerows(frame_rows)
    with f_summary.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summary_rows[0].keys()))
        w.writeheader()
        w.writerows(summary_rows)
    if vrows:
        with f_valid.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(vrows[0].keys()))
            w.writeheader()
            w.writerows(vrows)

    print(f"Wrote {f_frames.relative_to(PROJECT_ROOT)}")
    print(f"Wrote {f_summary.relative_to(PROJECT_ROOT)}")
    if vrows:
        print(f"Wrote {f_valid.relative_to(PROJECT_ROOT)}")
    if _warnings:
        print(f"\n{len(_warnings)} warning(s) were raised — re-read them before "
              f"using these numbers.")
    print()
    print("NOTE: these are ESTIMATES for the pictures the encoder never coded. "
          "They are intentionally NOT merged into results/raw_metrics.csv. "
          "Any BD-rate or figure derived from them must be labelled as "
          "reconstructed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
