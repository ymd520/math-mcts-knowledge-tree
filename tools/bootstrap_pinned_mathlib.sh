#!/usr/bin/env bash
# Bounded exact-commit mathlib cache recovery: NEVER silently change revision.
# Run from the root of a checked-out mathlib4 repository.
set -Eeuo pipefail
module_file="${1:-Mathlib/Algebra/Group/Basic.lean}"
if [[ ! "$module_file" =~ ^Mathlib/[A-Za-z0-9_/-]+\.lean$ ]]; then
  echo "Invalid Mathlib module filename: $module_file" >&2; exit 2
fi
if ! test -f "$module_file"; then
  echo "The pinned revision does not contain $module_file" >&2; exit 2
fi
module="${module_file%.lean}"
module="${module//\//.}"
echo "Pinned source module: $module"
echo "Actual toolchain: $(cat lean-toolchain)"
lake --version
for attempt in 1 2; do
  echo "Mathlib targeted cache attempt $attempt/2 (max 240 s per attempt)"
  if timeout 240 lake exe cache get "$module_file"; then
    echo "Mathlib targeted cache retrieval completed"
    exit 0
  fi
  sleep 3
done
echo "Using documented legacy cache endpoint for the same pinned source"
if MATHLIB_CACHE_DEBUG_USE_LEGACY=1 timeout 240 lake exe cache get "$module_file"; then
  echo "Legacy targeted retrieval completed"
  exit 0
fi
echo "Cache unavailable: falling back to targeted SOURCE compilation, not entire Mathlib"
if timeout 720 lake build "$module"; then
  echo "Mathlib pinned module source compilation succeeded"
  exit 0
fi
echo "ERROR: pinned Mathlib module could not be prepared; no theorem extraction is claimed" >&2
exit 1
