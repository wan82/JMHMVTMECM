#!/usr/bin/env python3
"""Pre-extract every Nth frame from each AI sequence YUV into a smaller YUV.

Background: VTM 23 and ECM 18 ship CTC AI configs with TemporalSubsampleRatio=8
(JVET CTC AI methodology — encode every 8th frame, since AI is all-intra and
adjacent intra frames give near-identical RD). HM 18 also accepts
--TemporalSubsampleRatio=8 on the CLI. JM 19, however, has no temporal
subsampling option — we pre-decimate the YUV instead.

To keep cross-encoder BD-rate honest, all four codecs must encode the SAME
8 source pictures. This script produces the JM-side input YUV:

    sequences/<Name>.yuv  (full sequence, used by HM/VTM/ECM AI + everyone RA)
            |
            v   pick frames 0, TSR, 2*TSR, ..., (N-1)*TSR
    sequences/<Name>_AI_TSR8.yuv  (only used by JM AI)

JM is then run with FrameRate = source_fps / TSR (= 6.25 for 50fps source) so
its kbps numbers come out on the same time base as HM/VTM/ECM.

Usage:
    python scripts/extract_ai_subsample.py            # all sequences in pilot.yaml
    python scripts/extract_ai_subsample.py BasketballDrill BlowingBubbles
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIGS_DIR = PROJECT_ROOT / "configs"
SEQUENCES_DIR = PROJECT_ROOT / "sequences"

# JVET VVC CTC AI subsample ratio. Hard-coded — if you change this, you must
# also update build_cmd_hm_vtm_ecm() in run_pilot.py.
TSR = 8


def yuv_frame_bytes(width: int, height: int, bit_depth: int,
                    chroma_format: int) -> int:
    """Bytes per frame for planar YUV. Supports 4:2:0 / 4:2:2 / 4:4:4 at
    8 or 10 bit."""
    if chroma_format == 420:
        luma = width * height
        chroma = (width // 2) * (height // 2) * 2  # U + V planes
    elif chroma_format == 422:
        luma = width * height
        chroma = (width // 2) * height * 2
    elif chroma_format == 444:
        luma = width * height
        chroma = width * height * 2
    else:
        raise ValueError(f"Unsupported chroma_format: {chroma_format}")

    samples = luma + chroma
    bytes_per_sample = 2 if bit_depth > 8 else 1
    return samples * bytes_per_sample


def load_pilot_cfg() -> dict:
    with open(CONFIGS_DIR / "pilot.yaml") as f:
        return yaml.safe_load(f)


def load_sequence_cfg(name: str) -> dict:
    p = CONFIGS_DIR / "sequences" / f"{name}.yaml"
    if not p.exists():
        raise FileNotFoundError(f"Sequence config missing: {p}")
    with open(p) as f:
        return yaml.safe_load(f)


def subsample_yuv(src: Path, dst: Path, frame_bytes: int,
                  num_input_frames: int, tsr: int) -> int:
    """Read every `tsr`-th frame from `src`, write to `dst`. Returns the
    number of frames written.

    `num_input_frames` is the window over which we subsample (e.g. 64 in
    pilot). So we write floor(num_input_frames / tsr) frames.
    """
    n_out = num_input_frames // tsr
    if n_out == 0:
        raise ValueError(
            f"num_input_frames={num_input_frames} < TSR={tsr}; nothing to write")

    with open(src, "rb") as f_in, open(dst, "wb") as f_out:
        for i in range(n_out):
            input_pos = i * tsr * frame_bytes
            f_in.seek(input_pos)
            buf = f_in.read(frame_bytes)
            if len(buf) != frame_bytes:
                raise IOError(
                    f"Short read at frame {i*tsr} of {src}: "
                    f"got {len(buf)} bytes, expected {frame_bytes}. "
                    f"Source YUV may have fewer than {num_input_frames} frames."
                )
            f_out.write(buf)
    return n_out


def process_sequence(name: str, num_input_frames: int) -> Path:
    seq = load_sequence_cfg(name)
    src = SEQUENCES_DIR / seq["yuv_filename"]
    if not src.exists():
        raise FileNotFoundError(f"Source YUV missing: {src}")

    dst_name = src.stem + f"_AI_TSR{TSR}.yuv"
    dst = SEQUENCES_DIR / dst_name

    fb = yuv_frame_bytes(
        seq["width"], seq["height"], seq["bit_depth"], seq["chroma_format"])
    src_size = src.stat().st_size
    src_frames = src_size // fb

    if num_input_frames > src_frames:
        raise ValueError(
            f"{src.name} has only {src_frames} frames but pilot wants "
            f"num_input_frames={num_input_frames}")

    n_written = subsample_yuv(src, dst, fb, num_input_frames, TSR)
    print(f"  {src.name} ({src_frames}f) -> {dst.name} "
          f"({n_written}f, TSR={TSR}, picks frames "
          f"{','.join(str(i*TSR) for i in range(n_written))})")
    return dst


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("sequences", nargs="*",
                    help="Sequence names to process. Default: all in pilot.yaml.")
    ap.add_argument("--input-window", type=int, default=None,
                    help="Override input frame window (default: pilot.yaml frames_to_encode).")
    args = ap.parse_args()

    pilot_cfg = load_pilot_cfg()
    num_input_frames = args.input_window or int(pilot_cfg["frames_to_encode"])
    seq_names = args.sequences or list(pilot_cfg["sequences"])

    print(f"Subsample window={num_input_frames} frames, TSR={TSR} "
          f"-> {num_input_frames // TSR} output frames per sequence\n")

    for name in seq_names:
        try:
            process_sequence(name, num_input_frames)
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR processing {name}: {e}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
