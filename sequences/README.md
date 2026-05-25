# Test sequences

This directory holds the raw YUV files used by the pilot. The YUV files
themselves are **not committed** to git (see `.gitignore`); only
`MANIFEST.csv` is tracked.

## Files required for the pilot

| Filename | Class | Size | Resolution | Frame rate | Source |
|---|---|---|---|---|---|
| `BasketballDrill_832x480_50.yuv` | C | ~286 MB | 832×480 | 50 fps | JVET CTC |
| `BlowingBubbles_416x240_50.yuv`  | D | ~72 MB  | 416×240 | 50 fps | JVET CTC |

## Where to get them

JVET CTC test sequences are distributed by Fraunhofer HHI, Leibniz University
Hannover, and related institutions. Common ways to obtain them:

- `ftp://hevc:US88Hula@ftp.tnt.uni-hannover.de/testsequences/` (mirror)
- Ask your advisor / lab — most reliable; verify with the MD5 below

## Integrity check

After placing the files in this directory, compute the MD5 and update the
corresponding YAML in `configs/sequences/`:

```bash
# Linux
md5sum BasketballDrill_832x480_50.yuv
md5sum BlowingBubbles_416x240_50.yuv

# macOS
md5 BasketballDrill_832x480_50.yuv
```

Once the MD5 is in `configs/sequences/<name>.yaml`, `run_pilot.py` will
verify it automatically at startup.

## Future extension (Class A)

```
Traffic_2560x1600_30_crop.yuv          ~1.2 GB
PeopleOnStreet_2560x1600_30_crop.yuv   ~1.2 GB
```

The pilot does **not** require these — add them only when extending to
the full CTC scope.
