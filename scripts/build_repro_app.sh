#!/usr/bin/env bash
set -euo pipefail

LABEL="${1:?usage: build_repro_app.sh <label>}"

ROOT="$(
    cd "$(dirname "$0")/.."
    pwd
)"

PY="${PYTHON:-python}"
BUNDLE_ID="${MACOS_BUNDLE_ID:-org.wamcoin.silentwallet}"
TARGET_ARCH="${MACOS_TARGET_ARCH:-$(uname -m)}"
ENTITLEMENTS="${MACOS_ENTITLEMENTS_FILE:-$ROOT/packaging/entitlements.plist}"
CODESIGN_IDENTITY="${MACOS_CODESIGN_IDENTITY:-}"

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
echo "Bundle ID: $BUNDLE_ID"
echo "Target arch: $TARGET_ARCH"
echo "SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH"
echo "========================================"

ARGS=(
    --clean
    --noconfirm
    --windowed
    --name "WAM Silent Wallet"
    --paths "$ROOT/src"
    --additional-hooks-dir "$ROOT/packaging/hooks"
    --collect-all coincurve
    --hidden-import coincurve._cffi_backend
    --osx-bundle-identifier "$BUNDLE_ID"
    --target-arch "$TARGET_ARCH"
    --distpath "$DIST"
    --workpath "$WORK"
    --specpath "$SPEC"
)

if [[ -n "$CODESIGN_IDENTITY" ]]; then
    test -f "$ENTITLEMENTS"

    ARGS+=(
        --codesign-identity "$CODESIGN_IDENTITY"
        --osx-entitlements-file "$ENTITLEMENTS"
    )

    echo "Signing identity: $CODESIGN_IDENTITY"
    echo "Entitlements: $ENTITLEMENTS"
else
    echo "Signing identity: ad-hoc"
fi

"$PY" -m PyInstaller \
    "${ARGS[@]}" \
    "$ROOT/app.py"

APP="$DIST/WAM Silent Wallet.app"

test -d "$APP"

codesign \
    --verify \
    --deep \
    --strict \
    --verbose=2 \
    "$APP"

if [[ -n "$CODESIGN_IDENTITY" ]]; then
    SIGN_INFO="$(
        codesign \
            -d \
            --verbose=4 \
            "$APP" \
            2>&1
    )"

    printf '%s\n' "$SIGN_INFO"

    grep -q "runtime" <<<"$SIGN_INFO" || {
        echo "FAIL — hardened runtime is not enabled"
        exit 1
    }

    echo "HARDENED RUNTIME: PASS"
fi

echo
echo "BUILD $LABEL: PASS"
echo "CODESIGN $LABEL: PASS"
echo "APP: $APP"
