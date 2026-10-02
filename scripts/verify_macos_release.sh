#!/usr/bin/env bash
set -euo pipefail

APP="${1:?usage: verify_macos_release.sh <app> [adhoc|developer-id]}"
MODE="${2:-adhoc}"

case "$MODE" in
    adhoc|developer-id) ;;
    *)
        echo "FAIL — unsupported signing mode: $MODE"
        exit 1
        ;;
esac

test -d "$APP"

INFO="$APP/Contents/Info.plist"
EXEC="$APP/Contents/MacOS/WAM Silent Wallet"

test -f "$INFO"
test -x "$EXEC"

echo "=== BUNDLE ID ==="

BUNDLE_ID="$(
    /usr/libexec/PlistBuddy \
        -c 'Print :CFBundleIdentifier' \
        "$INFO"
)"

echo "$BUNDLE_ID"

[[ "$BUNDLE_ID" == "org.wamcoin.silentwallet" ]] || {
    echo "FAIL — unexpected bundle identifier"
    exit 1
}

echo "BUNDLE ID: PASS"

echo
echo "=== ARCHITECTURE ==="

ARCHS="$(lipo -archs "$EXEC")"
echo "$ARCHS"

grep -qw "arm64" <<<"$ARCHS" || {
    echo "FAIL — arm64 executable missing"
    exit 1
}

echo "ARM64: PASS"

echo
echo "=== CODE SIGNATURE ==="

codesign \
    --verify \
    --deep \
    --strict \
    --verbose=2 \
    "$APP"

SIGN_INFO="$(
    codesign \
        -d \
        --verbose=4 \
        "$APP" \
        2>&1
)"

printf '%s\n' "$SIGN_INFO"

if [[ "$MODE" == "developer-id" ]]; then
    grep -q \
        "Authority=Developer ID Application:" \
        <<<"$SIGN_INFO" || {
            echo "FAIL — Developer ID authority missing"
            exit 1
        }

    grep -q "runtime" <<<"$SIGN_INFO" || {
        echo "FAIL — hardened runtime missing"
        exit 1
    }

    grep -q "Timestamp=" <<<"$SIGN_INFO" || {
        echo "FAIL — secure timestamp missing"
        exit 1
    }

    xcrun stapler validate "$APP"

    spctl \
        --assess \
        --type execute \
        --verbose=4 \
        "$APP"

    echo "DEVELOPER ID / RUNTIME / NOTARY: PASS"
else
    echo "AD-HOC SIGNATURE: PASS"
fi

echo
echo "=== BUNDLE CONTAMINATION ==="

BAD="$(
    find "$APP" -type f \
        \( \
            -name 'wallet.db' \
            -o -name 'wallet.db-*' \
            -o -name 'keys.wsp' \
            -o -name '.cookie' \
            -o -name '*.wspbak' \
            -o -name '.wallet-runtime.lock' \
            -o -name 'recovery-pending.json' \
            -o -name '.recovery-activation.json' \
        \) \
        -print
)"

if [[ -n "$BAD" ]]; then
    echo "$BAD"
    echo "FAIL — runtime state embedded in app"
    exit 1
fi

echo "NO RUNTIME STATE IN APP: PASS"

if [[ "${RUN_LAUNCH_SMOKE:-0}" == "1" ]]; then
    echo
    echo "=== CLEAN-HOME LAUNCH SMOKE ==="

    TMP="$(
        mktemp -d \
            "${TMPDIR:-/tmp}/wam-release-smoke.XXXXXX"
    )"

    trap 'rm -rf "$TMP"' EXIT

    mkdir -p \
        "$TMP/home" \
        "$TMP/data"

    HOME="$TMP/home" \
    WAM_SILENT_WALLET_DATA_DIR="$TMP/data" \
    "$EXEC" \
        >"$TMP/app.log" \
        2>&1 &

    PID=$!

    sleep 5

    if ! kill -0 "$PID" 2>/dev/null; then
        echo "FAIL — packaged app exited during launch smoke"
        cat "$TMP/app.log"
        wait "$PID" || true
        exit 1
    fi

    kill -TERM "$PID"

    for _ in {1..100}; do
        if ! kill -0 "$PID" 2>/dev/null; then
            break
        fi
        sleep 0.1
    done

    if kill -0 "$PID" 2>/dev/null; then
        kill -KILL "$PID" 2>/dev/null || true
        echo "FAIL — packaged app did not shut down"
        cat "$TMP/app.log"
        exit 1
    fi

    wait "$PID" || STATUS=$?
    STATUS="${STATUS:-0}"

    if [[ "$STATUS" -ne 0 && "$STATUS" -ne 143 ]]; then
        echo "FAIL — packaged app shutdown status: $STATUS"
        cat "$TMP/app.log"
        exit 1
    fi

    echo "PACKAGED APP CLEAN-HOME LAUNCH: PASS"
fi

echo
echo "========================================"
echo "MACOS RELEASE VERIFICATION: PASS"
echo "========================================"
