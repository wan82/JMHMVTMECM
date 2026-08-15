#!/usr/bin/env python3
"""One-off recovery: split a run directory that several run_pilot.py processes
shared by mistake into proper per-sequence run directories.

Why this exists
---------------
`make fastTestTop7` without SEQ used to expand its run name as shell
`fastTop7_$s$(TAG)`. With TAG=_nogbi that parses as the variable `$s_nogbi`
(undefined -> empty), not `${s}_nogbi`, so every sequence's process targeted the
single directory `runs/fastTop7_` and they raced over one jobs.csv. The Makefile
now uses `$${s}` and cannot do this again; this script cleans up the aftermath.

The encoder logs themselves are fine — only the bookkeeping is scrambled. This
copies each sequence's logs and bitstreams into `runs/fastTop7_<SEQ><suffix>/`
and writes a per-sequence jobs.csv with corrected paths, so the runs become
resumable and parseable like any normal run.

Safety: copies rather than moves, never overwrites an existing destination, and
skips any sequence whose jobs are not all DONE.

Usage
-----
    python scripts/salvage_shared_rundir.py \
        --shared runs/fastTop7_ \
        --sequences ParkScene,BQMall,BQSquare \
        --suffix _nogbi
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shared", required=True, type=Path,
                    help="the run dir several processes shared, e.g. runs/fastTop7_")
    ap.add_argument("--sequences", required=True,
                    help="comma-separated sequence names to extract")
    ap.add_argument("--suffix", default="_nogbi",
                    help="suffix for the new run dirs (default: _nogbi)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    shared = args.shared.resolve()
    jobs_csv = shared / "jobs.csv"
    if not jobs_csv.exists():
        sys.exit(f"ERROR: {jobs_csv} not found")
    runs_root = shared.parent
    rows = list(csv.DictReader(jobs_csv.open()))
    if not rows:
        sys.exit(f"ERROR: {jobs_csv} has no rows")

    rc = 0
    for seq in args.sequences.split(","):
        seq = seq.strip()
        dst = runs_root / f"fastTop7_{seq}{args.suffix}"
        mine = [r for r in rows if r["sequence"] == seq]

        if dst.exists():
            print(f"SKIP {seq}: {dst.name} already exists — not touching it")
            continue
        if not mine:
            print(f"SKIP {seq}: no rows for it in {jobs_csv.name} "
                  f"(it never ran; re-run this sequence)")
            rc = 1
            continue
        bad = [r for r in mine if r["status"] != "DONE"]
        if bad:
            print(f"SKIP {seq}: {len(bad)} job(s) not DONE "
                  f"({', '.join(r['job_id'] for r in bad)}) — re-run this sequence")
            rc = 1
            continue

        if args.dry_run:
            print(f"WOULD extract {seq}: {len(mine)} jobs -> {dst.name}")
            continue

        (dst / "logs").mkdir(parents=True)
        (dst / "bitstreams").mkdir()
        n_log = n_bin = 0
        for r in mine:
            for sub, key in (("logs", "log_path"), ("bitstreams", "bitstream_path")):
                src = shared / sub / Path(r[key]).name
                if src.exists():
                    shutil.copy2(src, dst / sub / src.name)
                    if sub == "logs":
                        n_log += 1
                    else:
                        n_bin += 1
                r[key] = str(dst / sub / Path(r[key]).name)
        with (dst / "jobs.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(mine)
        print(f"OK   {seq}: {n_log} logs, {n_bin} bitstreams -> {dst.name}")

    if not args.dry_run:
        print(f"\nOriginals left untouched in {shared}. Verify the new dirs, then "
              f"delete it manually.")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
