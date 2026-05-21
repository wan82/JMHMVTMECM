#!/usr/bin/env python3
"""Sanity check: run a tiny encode per encoder to verify the build.

Uses BlowingBubbles 16 frames AI QP37 — the cheapest possible workload.
Just verifies each binary produces a non-zero-size bitstream and exits cleanly.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BIN_DIR = PROJECT_ROOT / "bin"
SEQ_DIR = PROJECT_ROOT / "sequences"
CFG_DIR = PROJECT_ROOT / "configs"

SEQ_YAML = CFG_DIR / "sequences" / "BlowingBubbles.yaml"
FRAMES = 16
QP = 37


def main() -> int:
    if not SEQ_YAML.exists():
        print(f"ERROR: missing {SEQ_YAML}", file=sys.stderr)
        return 1
    seq = yaml.safe_load(SEQ_YAML.read_text())
    yuv = SEQ_DIR / seq["yuv_filename"]
    if not yuv.exists():
        print(f"ERROR: sequence YUV not found at {yuv}", file=sys.stderr)
        print("Place the YUV in sequences/ first (see sequences/README.md).",
              file=sys.stderr)
        return 1

    encoders = ["jm", "hm", "vtm", "ecm"]
    ok = 0
    fail = 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for enc in encoders:
            print(f"\n=== Sanity check: {enc.upper()} ===")
            if enc == "jm":
                binary = BIN_DIR / "lencod"
                cfg = CFG_DIR / "jm" / "encoder_JM_Intra_HE.cfg"
                bs = tmp / f"jm_test.264"
                cmd = [str(binary), "-d", str(cfg),
                       "-p", f"InputFile={yuv}",
                       "-p", f"OutputFile={bs}",
                       "-p", "ReconFile=",
                       "-p", f"SourceWidth={seq['width']}",
                       "-p", f"SourceHeight={seq['height']}",
                       "-p", f"OutputWidth={seq['width']}",
                       "-p", f"OutputHeight={seq['height']}",
                       "-p", f"FrameRate={seq['fps']}",
                       "-p", f"FramesToBeEncoded={FRAMES}",
                       "-p", f"QPISlice={QP}",
                       "-p", "IntraPeriod=1", "-p", "IDRPeriod=1"]
            else:
                binmap = {"hm": "TAppEncoder", "vtm": "EncoderApp_VTM",
                          "ecm": "EncoderApp_ECM"}
                cfgmap = {"hm": "encoder_intra_main.cfg",
                          "vtm": "encoder_intra_vtm.cfg",
                          "ecm": "encoder_intra_ecm.cfg"}
                binary = BIN_DIR / binmap[enc]
                cfg = CFG_DIR / enc / cfgmap[enc]
                bs = tmp / f"{enc}_test.bin"
                cmd = [str(binary), "-c", str(cfg),
                       f"--InputFile={yuv}", f"--BitstreamFile={bs}",
                       f"--SourceWidth={seq['width']}",
                       f"--SourceHeight={seq['height']}",
                       f"--FrameRate={seq['fps']}",
                       f"--InputBitDepth={seq['bit_depth']}",
                       f"--InputChromaFormat={seq['chroma_format']}",
                       f"--FramesToBeEncoded={FRAMES}",
                       f"--QP={QP}", "--IntraPeriod=1",
                       "--ReconFile="]
            if not binary.exists():
                print(f"  SKIP: binary missing: {binary}")
                fail += 1
                continue
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True,
                                      timeout=600)
            except subprocess.TimeoutExpired:
                print(f"  FAIL: timeout after 600s")
                fail += 1
                continue
            if proc.returncode != 0:
                print(f"  FAIL: exit code {proc.returncode}")
                print("  stderr tail:")
                for line in proc.stderr.splitlines()[-10:]:
                    print(f"    {line}")
                fail += 1
                continue
            if not bs.exists() or bs.stat().st_size == 0:
                print(f"  FAIL: empty/missing bitstream {bs}")
                fail += 1
                continue
            print(f"  OK ({bs.stat().st_size} bytes)")
            ok += 1

    print(f"\nSummary: {ok} ok, {fail} failed.")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
