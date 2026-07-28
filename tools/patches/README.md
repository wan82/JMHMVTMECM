# Patches

This directory stores compatibility patches for the encoder source trees under
`tools/`.

## Current status: kept for reference, not auto-applied

This project currently **commits the modifications directly** into the source
trees under `tools/` (see comments in `.gitignore`). The patch files here exist
for two reasons:

1. **Diff readability.** They record every modification in standard unified-diff
   format — useful for code review, for writing the paper's methodology
   section, or for quickly seeing "what did we change" outside `git log`.
2. **Reapply-ability.** If the source trees are ever replaced (e.g. upgrading
   to JM-19.2, or a future maintainer unzipping a fresh source archive over
   them), these patches can be applied again without re-doing the work by hand.

`scripts/build_all.sh` does **not** auto-apply these patches today (applying
them to an already-modified tree would either fail or double-apply). This is
intentional.

## File list

| File | Targets | What it changes |
|---|---|---|
| `jm_arm_macos.patch` | `tools/JM-JM-19.1/` | Gates the `-msse4.1` compile flag so it only fires on x86/x86_64 |
| `hm_arm_macos.patch` | `tools/HM-HM-18.0/` | Same as above, plus arm64 guards around the SSE/AVX source globs and per-file compile flags |

VTM-23.11 and ECM-18.0 already handle arm64 in their upstream CMakeLists, so
**no patches are needed** for them.

## Re-applying on a pristine source tree

If a future maintainer accidentally overwrites `tools/JM-JM-19.1/` or
`tools/HM-HM-18.0/` (for example by re-extracting a source zip):

```bash
cd tools/JM-JM-19.1
git apply ../patches/jm_arm_macos.patch

cd ../HM-HM-18.0
git apply ../patches/hm_arm_macos.patch
```

`git apply` refuses to apply a patch that is already applied (it prints
"patch does not apply"), so **rerunning is idempotent and safe**.

If you prefer the standard `patch` tool instead of `git apply`:

```bash
cd tools/JM-JM-19.1
patch -p1 < ../patches/jm_arm_macos.patch
```

## Switching to a "patch-driven" workflow (if needed later)

If the repository ever needs to shrink below 200 MB, you can switch to:

1. Don't commit the source trees under `tools/` (add `tools/*/` to
   `.gitignore`, but allow-list `tools/patches/` and `tools/README.md`).
2. Have `scripts/build_all.sh` auto-apply these patches before configuring
   CMake (the script already has an `apply_patch_if_present` helper — change
   it from "ARM-only" to "always" and you're done).
3. The maintainer downloads/extracts the encoder source trees into `tools/`
   themselves, and the build script applies patches on top.

The repo would then shrink to a few MB, at the cost of asking the maintainer
to prepare `tools/` by hand (zip download links go in `tools/README.md`).
There's no need to do this in the current phase.

## When you upgrade source versions

If you upgrade to JM-19.2 / HM-19.0 / etc., these patches will most likely
**no longer apply cleanly** — context line numbers will have shifted, or the
upstream may have added arm64 guards itself. To handle that:

1. First try `git apply --check` to see whether the patch still applies.
2. If it fails, manually redo the equivalent change in the new source tree.
3. Regenerate the patch with `diff -u` against the new pristine source and
   replace the old patch file here.
4. Record the version change in `HANDOFF.md`.

---

## `vtm_head_frames.patch` / `ecm_head_frames.patch`

Functional patches (all platforms, auto-applied by `build_all.sh`) that add a
head-frames early-stop hook to `source/Lib/EncoderLib/EncGOP.cpp` in VTM and
ECM. When the env var `PILOT_MAX_CODED_PICS=N` is set, `compressGOP()` exits
cleanly after coding the first N pictures in CODING order (N=7 -> POC
0,32,16,8,4,2,1 for a GOP-32 RA hierarchy). Used by `make encode N` (see the
top-level README "Fast mode" section) to cap the expensive VTM/ECM encoders
while JM/HM still encode in full. Unset / <=0 => normal full encode.

The change is committed directly in the working tree, so a plain rebuild
(`make build-vtm build-ecm`) already carries it; the patch files exist for
documentation and for re-applying to a pristine re-checkout:

```
cd tools/VVCSoftware_VTM-VTM-23.11 && git apply ../patches/vtm_head_frames.patch
cd tools/ECM-ECM-18.0             && git apply ../patches/ecm_head_frames.patch
```
