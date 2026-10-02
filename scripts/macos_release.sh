#!/usr/bin/env bash
set -euo pipefail

ROOT="$(
    cd "$(dirname "$0")/.."
    pwd
)"

cd "$ROOT"

PY="${PYTHON:-$ROOT/.venv/bin/python}"
MODE="${RELEASE_MODE:-adhoc}"
BUNDLE_ID="${MACOS_BUNDLE_ID:-org.wamcoin.silentwallet}"
ARCH="${MACOS_TARGET_ARCH:-arm64}"
RUN_LAUNCH_SMOKE="${RUN_LAUNCH_SMOKE:-1}"

case "$MODE" in
    adhoc|developer-id) ;;
    *)
        echo "FAIL — RELEASE_MODE must be adhoc or developer-id"
        exit 1
        ;;
esac

VERSION="${RELEASE_VERSION:-}"

if [[ -z "$VERSION" ]]; then
    VERSION="$(
        "$PY" - <<'PY'
import tomllib

with open(
    "pyproject.toml",
    "rb",
) as handle:
    data = tomllib.load(handle)

print(
    data["project"]["version"]
)
PY
    )"
fi

[[ "$VERSION" =~ ^[0-9]+(\.[0-9]+){1,3}([.-][A-Za-z0-9]+)*$ ]] || {
    echo "FAIL — invalid RELEASE_VERSION: $VERSION"
    exit 1
}

LABEL="release-$VERSION"
OUTPUT="$ROOT/release/$VERSION"
STAGE="$OUTPUT/dmg-stage"
APP="$ROOT/.repro-build/$LABEL/dist/WAM Silent Wallet.app"
ZIP="$OUTPUT/WAM-Silent-Wallet-$VERSION-macOS-$ARCH.zip"
DMG="$OUTPUT/WAM-Silent-Wallet-$VERSION-macOS-$ARCH.dmg"
MANIFEST="$OUTPUT/release-manifest.json"
CHECKSUMS="$OUTPUT/SHA256SUMS.txt"

rm -rf "$OUTPUT"
mkdir -p "$OUTPUT"

export MACOS_BUNDLE_ID="$BUNDLE_ID"
export MACOS_TARGET_ARCH="$ARCH"

if [[ "$MODE" == "developer-id" ]]; then
    : "${MACOS_CODESIGN_IDENTITY:?MACOS_CODESIGN_IDENTITY is required}"
    : "${APPLE_ID:?APPLE_ID is required}"
    : "${APPLE_TEAM_ID:?APPLE_TEAM_ID is required}"
    : "${APPLE_APP_PASSWORD:?APPLE_APP_PASSWORD is required}"
else
    unset MACOS_CODESIGN_IDENTITY || true
fi

echo "========================================"
echo "WAM SILENT WALLET RELEASE"
echo "Version: $VERSION"
echo "Mode: $MODE"
echo "Bundle ID: $BUNDLE_ID"
echo "Architecture: $ARCH"
echo "========================================"

PYTHON="$PY" \
    bash scripts/build_repro_app.sh \
    "$LABEL"

NOTARIZED=0

if [[ "$MODE" == "developer-id" ]]; then
    echo
    echo "=== NOTARIZATION UPLOAD ==="

    UPLOAD_ZIP="$OUTPUT/notary-upload.zip"

    ditto \
        -c \
        -k \
        --sequesterRsrc \
        --keepParent \
        "$APP" \
        "$UPLOAD_ZIP"

    NOTARY_JSON="$OUTPUT/notary-result.json"

    xcrun notarytool submit \
        "$UPLOAD_ZIP" \
        --apple-id "$APPLE_ID" \
        --team-id "$APPLE_TEAM_ID" \
        --password "$APPLE_APP_PASSWORD" \
        --wait \
        --output-format json \
        >"$NOTARY_JSON"

    cat "$NOTARY_JSON"

    "$PY" - "$NOTARY_JSON" <<'PY'
import json
from pathlib import Path
import sys

data = json.loads(
    Path(
        sys.argv[1]
    ).read_text(
        encoding="utf-8"
    )
)

if data.get("status") != "Accepted":
    raise SystemExit(
        "FAIL — Apple notarization was not Accepted"
    )

print(
    "APPLE NOTARIZATION: ACCEPTED"
)
PY

    xcrun stapler staple "$APP"
    xcrun stapler validate "$APP"

    rm -f "$UPLOAD_ZIP"

    NOTARIZED=1
fi

echo
echo "=== VERIFY FINAL APP ==="

RUN_LAUNCH_SMOKE="$RUN_LAUNCH_SMOKE" \
    bash scripts/verify_macos_release.sh \
    "$APP" \
    "$MODE"

echo
echo "=== CREATE ZIP ==="

ditto \
    -c \
    -k \
    --sequesterRsrc \
    --keepParent \
    "$APP" \
    "$ZIP"

echo
echo "=== CREATE DMG ==="

rm -rf "$STAGE"
mkdir -p "$STAGE"

ditto \
    "$APP" \
    "$STAGE/WAM Silent Wallet.app"

ln -s \
    /Applications \
    "$STAGE/Applications"

hdiutil create \
    -quiet \
    -volname "WAM Silent Wallet $VERSION" \
    -srcfolder "$STAGE" \
    -ov \
    -format UDZO \
    "$DMG"

rm -rf "$STAGE"

echo
echo "=== COPY RELEASE EVIDENCE ==="

cp sbom.cdx.json "$OUTPUT/sbom.cdx.json"
cp supply-chain.lock.json "$OUTPUT/supply-chain.lock.json"
cp artifacts.lock.json "$OUTPUT/artifacts.lock.json"
cp requirements-hashed.txt "$OUTPUT/requirements-hashed.txt"

echo
echo "=== RELEASE MANIFEST ==="

MANIFEST_ARGS=(
    create
    --root "$ROOT"
    --app "$APP"
    --artifact "$ZIP"
    --artifact "$DMG"
    --artifact "$OUTPUT/sbom.cdx.json"
    --artifact "$OUTPUT/supply-chain.lock.json"
    --artifact "$OUTPUT/artifacts.lock.json"
    --artifact "$OUTPUT/requirements-hashed.txt"
    --version "$VERSION"
    --signing-mode "$MODE"
    --output "$MANIFEST"
)

if [[ "$NOTARIZED" == "1" ]]; then
    MANIFEST_ARGS+=(--notarized)
fi

"$PY" -m scripts.release_manifest \
    "${MANIFEST_ARGS[@]}"

"$PY" -m scripts.release_manifest \
    verify \
    --root "$ROOT" \
    --manifest "$MANIFEST"

echo
echo "=== SHA256SUMS ==="

(
    cd "$OUTPUT"

    shasum -a 256 \
        "$(basename "$ZIP")" \
        "$(basename "$DMG")" \
        release-manifest.json \
        sbom.cdx.json \
        supply-chain.lock.json \
        artifacts.lock.json \
        requirements-hashed.txt \
        >SHA256SUMS.txt
)

cat "$CHECKSUMS"

echo
echo "========================================"
echo "MACOS RELEASE ENGINEERING: PASS"
echo "MODE: $MODE"
echo "NOTARIZED: $NOTARIZED"
echo "OUTPUT: $OUTPUT"
echo "========================================"
