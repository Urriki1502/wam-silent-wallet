#!/usr/bin/env bash
set -euo pipefail

LABEL="${1:?usage: build_repro_app.sh <label>}"

ROOT="$(
    cd "$(dirname "$0")/.."
    pwd
)"

PY="${PYTHON:-python}"

BUILD_ROOT="$ROOT/.repro-build/$LABEL"
DIST="$BUILD_ROOT/dist"
WORK="$BUILD_ROOT/work"
SPEC="$BUILD_ROOT/spec"

export SOURCE_DATE_EPOCH="$(
    git -C "$ROOT" log -1 --format=%ct
)"

export PYTHONHASHSEED=0
export TZ=UTC
export LC_ALL=C
export LANG=C
export PYTHONDONTWRITEBYTECODE=1

rm -rf "$BUILD_ROOT"

mkdir -p \
    "$DIST" \
    "$WORK" \
    "$SPEC"

echo "========================================"
echo "REPRO BUILD: $LABEL"
echo "Python: $("$PY" --version)"
echo "SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH"
echo "========================================"

"$PY" -m PyInstaller \
    --clean \
    --noconfirm \
    --windowed \
    --name "WAM Silent Wallet" \
    --paths "$ROOT/src" \
    --additional-hooks-dir "$ROOT/packaging/hooks" \
    --collect-all coincurve \
    --hidden-import coincurve._cffi_backend \
    --distpath "$DIST" \
    --workpath "$WORK" \
    --specpath "$SPEC" \
    "$ROOT/app.py"

APP="$DIST/WAM Silent Wallet.app"

test -d "$APP"

codesign \
    --verify \
    --deep \
    --strict \
    "$APP"

echo
echo "BUILD $LABEL: PASS"
echo "CODESIGN $LABEL: PASS"
echo "APP: $APP"
