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

BUNDLE_ID="${MACOS_BUNDLE_ID:-org.wamcoin.silentwallet}"
SIGNING_IDENTITY="${MACOS_SIGNING_IDENTITY:-}"
ENTITLEMENTS_FILE="${MACOS_ENTITLEMENTS_FILE:-$ROOT/packaging/macos/entitlements.plist}"

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
echo "Bundle ID: $BUNDLE_ID"

PYINSTALLER_ARGS=(
    --clean
    --noconfirm
    --windowed
    --name "WAM Silent Wallet"
    --osx-bundle-identifier "$BUNDLE_ID"
    --paths "$ROOT/src"
    --additional-hooks-dir "$ROOT/packaging/hooks"
    --collect-all coincurve
    --hidden-import coincurve._cffi_backend
    --distpath "$DIST"
    --workpath "$WORK"
    --specpath "$SPEC"
)

if [[ -n "$SIGNING_IDENTITY" ]]; then
    test -f "$ENTITLEMENTS_FILE"

    export PYINSTALLER_STRICT_BUNDLE_CODESIGN_ERROR=1

    PYINSTALLER_ARGS+=(
        --codesign-identity "$SIGNING_IDENTITY"
        --osx-entitlements-file "$ENTITLEMENTS_FILE"
    )

    echo "Signing: Developer ID"
    echo "Entitlements: $ENTITLEMENTS_FILE"
else
    echo "Signing: PyInstaller ad-hoc"
fi

echo "========================================"

"$PY" -m PyInstaller \
    "${PYINSTALLER_ARGS[@]}" \
    "$ROOT/app.py"

APP="$DIST/WAM Silent Wallet.app"

test -d "$APP"

/usr/bin/codesign \
    --verify \
    --deep \
    --strict \
    --verbose=4 \
    "$APP"

if [[ -n "$SIGNING_IDENTITY" ]]; then
    DETAILS="$(
        /usr/bin/codesign \
            --display \
            --verbose=4 \
            "$APP" \
            2>&1
    )"

    grep -F "Identifier=$BUNDLE_ID" \
        <<<"$DETAILS" >/dev/null

    grep -F "Authority=Developer ID Application:" \
        <<<"$DETAILS" >/dev/null

    grep -F "runtime" \
        <<<"$DETAILS" >/dev/null

    grep -F "Timestamp=" \
        <<<"$DETAILS" >/dev/null

    if grep -F "Signature=adhoc" \
        <<<"$DETAILS" >/dev/null; then
        echo "RELEASE SIGNATURE IS AD-HOC"
        exit 1
    fi

    echo "DEVELOPER ID / HARDENED RUNTIME: PASS"
fi

echo
echo "BUILD $LABEL: PASS"
echo "CODESIGN $LABEL: PASS"
echo "APP: $APP"
