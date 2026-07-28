#!/usr/bin/env bash
# Build JM / HM / VTM / ECM reference encoders.
# Cross-platform with two generator strategies:
#
#   macOS  → CMake Xcode generator + xcodebuild
#            (avoids the x86-only `-msse4.1` flag baked into some encoder
#             CMakeLists; xcodebuild lets the Apple toolchain decide).
#   Linux  → CMake default Makefile generator
#            (standard `make -j$(nproc)` build).
#
# Usage:
#   ./scripts/build_all.sh             # build all four
#   ./scripts/build_all.sh jm hm       # build a subset
#
# Tools layout it assumes (either is fine):
#   tools/JM-JM-19.1/                          (under project)
#   tools/HM-HM-18.0/
#   tools/VVCSoftware_VTM-VTM-23.11/
#   tools/ECM-ECM-18.0/
#
# Or set TOOLS_DIR to an external folder containing the four trees.
#
# Produces:
#   bin/lencod            (JM encoder)
#   bin/TAppEncoder       (HM encoder)
#   bin/EncoderApp_VTM    (VTM encoder, renamed to avoid collision)
#   bin/EncoderApp_ECM    (ECM encoder, renamed)
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLS_DIR="${TOOLS_DIR:-$PROJECT_ROOT/tools}"
BIN_DIR="$PROJECT_ROOT/bin"
PATCH_DIR="$PROJECT_ROOT/tools/patches"

mkdir -p "$BIN_DIR"

# --- platform detection ---
UNAME_S="$(uname -s)"
UNAME_M="$(uname -m)"
case "$UNAME_S" in
  Darwin) PLATFORM=macos ;;
  Linux)  PLATFORM=linux ;;
  *)      echo "ERROR: unsupported platform: $UNAME_S" >&2; exit 1 ;;
esac

# Parallelism
if [ "$PLATFORM" = "macos" ]; then
  NPROC="$(sysctl -n hw.ncpu)"
else
  NPROC="$(nproc)"
fi
echo "Platform: $PLATFORM ($UNAME_M), using $NPROC parallel jobs"

# Verify Xcode CLI tools on macOS (xcodebuild is required for the Xcode generator)
if [ "$PLATFORM" = "macos" ]; then
  if ! command -v xcodebuild >/dev/null 2>&1; then
    echo "ERROR: xcodebuild not found." >&2
    echo "       Install Xcode (App Store) or run: xcode-select --install" >&2
    exit 1
  fi
fi

# --- helper: apply patch if present ---
apply_patch_if_present() {
  local src_dir="$1"
  local patch_name="$2"
  local patch_file="$PATCH_DIR/$patch_name"
  if [ -f "$patch_file" ]; then
    echo "Applying patch: $patch_name"
    (cd "$src_dir" && git apply --check "$patch_file" 2>/dev/null && git apply "$patch_file") \
      || echo "  (already applied or not applicable)"
  fi
}

# --- helper: ad-hoc re-sign a binary on macOS ---
# A binary produced by xcodebuild and then `cp`-ed into bin/ can be SIGKILLed by
# AMFI on launch ("Killed: 9", exit -9, no output) because its ad-hoc signature
# doesn't validate at the new path. Re-signing in place at the final location
# fixes it, and clearing xattrs removes any quarantine flag. No-op off macOS.
resign_macos() {
  local bin="$1"
  if [ "$PLATFORM" = "macos" ]; then
    codesign --force --sign - "$bin" 2>/dev/null || true
    xattr -cr "$bin" 2>/dev/null || true
  fi
}

# --- locate source trees ---
locate_src() {
  local pattern="$1"
  local match
  match="$(find "$TOOLS_DIR" -maxdepth 1 -type d -name "$pattern" 2>/dev/null | head -n1)"
  if [ -z "$match" ]; then
    echo "ERROR: cannot find source tree matching '$pattern' under $TOOLS_DIR" >&2
    exit 1
  fi
  echo "$match"
}

# ---------------------------------------------------------------------------
# Core builder: configures and builds a single target with platform-aware
# generator choice. Caller passes:
#   $1 = source dir (absolute path)
#   $2 = build dir name under source (e.g. "build")
#   $3 = CMake target name (e.g. "lencod", "TAppEncoder", "EncoderApp")
# ---------------------------------------------------------------------------
cmake_configure_and_build() {
  local src="$1"
  local build_subdir="$2"
  local target="$3"

  # Decide the generator we want for this run.
  local want_gen
  if [ "$PLATFORM" = "macos" ]; then
    want_gen="Xcode"
  else
    want_gen="Unix Makefiles"
  fi

  (
    cd "$src"

    # If a previous build used a different generator, wipe the build dir.
    # CMake refuses to mix generators in the same build tree.
    local cache="$build_subdir/CMakeCache.txt"
    if [ -f "$cache" ]; then
      local prev_gen
      prev_gen="$(grep -E '^CMAKE_GENERATOR:INTERNAL=' "$cache" \
                  | cut -d= -f2- || true)"
      if [ -n "$prev_gen" ] && [ "$prev_gen" != "$want_gen" ]; then
        echo "  Generator switched: '$prev_gen' -> '$want_gen' — wiping $build_subdir/"
        rm -rf "$build_subdir"
      fi
    fi

    mkdir -p "$build_subdir"
    cd "$build_subdir"

    if [ "$PLATFORM" = "macos" ]; then
      # Xcode is a multi-config generator; CMAKE_BUILD_TYPE is ignored.
      # Build config is selected at build time via --config Release.
      cmake .. -G Xcode
      cmake --build . --config Release --target "$target" --parallel "$NPROC"
    else
      # Linux: default Makefile generator
      cmake .. -DCMAKE_BUILD_TYPE=Release
      cmake --build . --target "$target" --parallel "$NPROC"
    fi
  )
}

# ---------------------------------------------------------------------------
# Find a freshly built binary anywhere under the source tree.
# Xcode generator places outputs under build/<target>/Release/ or
# bin/Release-something/; Makefile generator places them in bin/ directly.
# We search broadly and pick the most recently modified executable matching
# the expected name, restricted to release-style paths.
# ---------------------------------------------------------------------------
locate_built_binary() {
  local src="$1"
  local name_glob="$2"   # e.g. "lencod" or "EncoderApp"

  # Prefer release-flavoured paths. Try several common patterns.
  local candidates=()
  while IFS= read -r p; do
    candidates+=("$p")
  done < <(find "$src" -type f -perm -u+x \
              \( -name "$name_glob" -o -name "${name_glob}.exe" \) \
              2>/dev/null | grep -viE "(debug|dsym|Debug)" || true)

  if [ "${#candidates[@]}" -eq 0 ]; then
    return 1
  fi

  # Pick the most recently modified one (the binary just built).
  # macOS `stat -f` differs from Linux `stat -c`; use `ls -t` which is portable.
  printf "%s\n" "${candidates[@]}" | xargs ls -t 2>/dev/null | head -n1
}

# ---------------------------------------------------------------------------
# Per-encoder builders
# ---------------------------------------------------------------------------
build_jm() {
  echo ""
  echo "=========================================="
  echo "  Building JM"
  echo "=========================================="
  local src
  src="$(locate_src 'JM-JM-*')"
  echo "Source: $src"
  apply_patch_if_present "$src" "jm_arm_macos.patch"

  cmake_configure_and_build "$src" "build" "lencod"

  local lencod
  if ! lencod="$(locate_built_binary "$src" "lencod")"; then
    echo "ERROR: lencod binary not found after build" >&2; exit 1
  fi
  cp "$lencod" "$BIN_DIR/lencod"
  chmod +x "$BIN_DIR/lencod"
  resign_macos "$BIN_DIR/lencod"
  echo "JM binary: $BIN_DIR/lencod"
}

build_hm() {
  echo ""
  echo "=========================================="
  echo "  Building HM"
  echo "=========================================="
  local src
  src="$(locate_src 'HM-HM-*')"
  echo "Source: $src"
  apply_patch_if_present "$src" "hm_arm_macos.patch"

  cmake_configure_and_build "$src" "build" "TAppEncoder"

  local tapp
  if ! tapp="$(locate_built_binary "$src" "TAppEncoder")"; then
    echo "ERROR: TAppEncoder binary not found after build" >&2; exit 1
  fi
  cp "$tapp" "$BIN_DIR/TAppEncoder"
  chmod +x "$BIN_DIR/TAppEncoder"
  resign_macos "$BIN_DIR/TAppEncoder"
  echo "HM binary: $BIN_DIR/TAppEncoder"
}

build_vvc_like() {
  local label="$1"          # VTM or ECM
  local pattern="$2"        # source dir pattern
  local out_name="$3"       # output binary name

  echo ""
  echo "=========================================="
  echo "  Building $label"
  echo "=========================================="
  local src
  src="$(locate_src "$pattern")"
  echo "Source: $src"

  local lower
  lower="$(echo "$label" | tr '[:upper:]' '[:lower:]')"

  # ARM macOS patches if any
  if [ "$PLATFORM" = "macos" ] && [ "$UNAME_M" = "arm64" ]; then
    apply_patch_if_present "$src" "${lower}_arm_macos.patch"
  fi

  # codec-comparison-pilot: head-frames early-stop hook in EncGOP.cpp (all
  # platforms). Enables `make encode N` to cap VTM/ECM at N coded pictures via
  # the PILOT_MAX_CODED_PICS env var. Harmless if the working-tree source
  # already carries the change (git apply --check fails, we skip) — the working
  # tree is the source of truth for the build.
  apply_patch_if_present "$src" "${lower}_head_frames.patch"

  # codec-comparison-pilot: ECM-only. Raise MAX_CCSAO_CTU_NUM (256 -> 4096) so
  # CCSAO can handle 4K (Class A: 3840x2160 = 510 CTUs at CTU128). No VTM
  # equivalent exists, so this is a no-op for the VTM build.
  apply_patch_if_present "$src" "${lower}_ccsao_4k.patch"

  cmake_configure_and_build "$src" "build" "EncoderApp"

  local enc
  if ! enc="$(locate_built_binary "$src" "EncoderApp")"; then
    echo "ERROR: $label EncoderApp binary not found after build" >&2; exit 1
  fi
  cp "$enc" "$BIN_DIR/$out_name"
  chmod +x "$BIN_DIR/$out_name"
  resign_macos "$BIN_DIR/$out_name"
  echo "$label binary: $BIN_DIR/$out_name"
}

build_vtm() {
  build_vvc_like "VTM" 'VVCSoftware_VTM-VTM-*' 'EncoderApp_VTM'
}

build_ecm() {
  build_vvc_like "ECM" 'ECM-ECM-*' 'EncoderApp_ECM'
}

# --- main ---
TARGETS=("$@")
if [ "${#TARGETS[@]}" -eq 0 ]; then
  TARGETS=(jm hm vtm ecm)
fi

for t in "${TARGETS[@]}"; do
  case "$t" in
    jm)  build_jm  ;;
    hm)  build_hm  ;;
    vtm) build_vtm ;;
    ecm) build_ecm ;;
    *)   echo "ERROR: unknown target '$t' (use jm|hm|vtm|ecm)" >&2; exit 1 ;;
  esac
done

echo ""
echo "Build summary:"
ls -lh "$BIN_DIR"
