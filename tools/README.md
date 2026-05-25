# Encoder source trees

`scripts/build_all.sh` looks for the four encoder source trees under this
directory (or under whatever `$TOOLS_DIR` points to), matched by name glob.

## Expected directory layout

```
tools/
├── JM-JM-19.1/                     (or JM-JM-19.x)
├── HM-HM-18.0/                     (or HM-HM-18.x)
├── VVCSoftware_VTM-VTM-23.11/      (or VTM-23.x)
├── ECM-ECM-18.0/                   (or ECM-ECM-18.x / 17.x)
└── patches/                        (optional — see below)
```

## Two ways to provide the source code

### Option A — copy into this directory

```bash
cp -r /path/to/JM-JM-19.1                   tools/
cp -r /path/to/HM-HM-18.0                   tools/
cp -r /path/to/VVCSoftware_VTM-VTM-23.11    tools/
cp -r /path/to/ECM-ECM-18.0                 tools/
```

### Option B — point to an external directory (recommended)

```bash
TOOLS_DIR=/path/to/JM_HM_VTM_ECM make build
```

If you already have the four source trees in a shared location and don't
want to duplicate them, this is the cleaner option. The build script reads
`TOOLS_DIR` from the environment and looks for the sources there instead.

## Patches (ARM macOS compatibility fixes)

If an encoder fails to build on Apple Silicon, drop a patch file at
`tools/patches/<encoder-lowercase>_arm_macos.patch`, e.g.:

- `tools/patches/ecm_arm_macos.patch`
- `tools/patches/vtm_arm_macos.patch`

The build script will run `git apply` on the patch inside the corresponding
source tree before invoking CMake. If the patch has already been applied,
or upstream has already merged the equivalent fix, the script logs a note
and continues without erroring out.

## Pinned versions

The exact versions used for the pilot baseline:

| Encoder | Tag |
|---|---|
| JM  | JM-19.1 |
| HM  | HM-18.0 |
| VTM | VTM-23.11 |
| ECM | ECM-18.0 |

These versions are also recorded in `HANDOFF.md`. **Do not** upgrade in
place — if you need to change a version, treat it as a new baseline run
to keep cross-encoder comparisons valid.
