#!/usr/bin/env bash
set -euo pipefail

REPO="${WAM_GITHUB_REPO:-Urriki1502/wam-silent-wallet}"

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

need() {
    command -v "$1" >/dev/null 2>&1 || fail "missing command: $1"
}

set_secret_text() {
    local name="$1"
    local value="$2"

    printf '%s' "$value" | gh secret set "$name" --repo "$REPO" >/dev/null
    printf 'SET %s\n' "$name"
}

set_secret_b64_file() {
    local name="$1"
    local path="$2"

    base64 < "$path" | tr -d '\n' | gh secret set "$name" --repo "$REPO" >/dev/null
    printf 'SET %s\n' "$name"
}

need gh
need security
need base64
need openssl

gh auth status >/dev/null 2>&1     || fail "GitHub CLI is not authenticated; run: gh auth login"

gh repo view "$REPO" >/dev/null 2>&1     || fail "cannot access repository: $REPO"

IDENTITY="${WAM_SIGNING_IDENTITY:-}"
if [[ -z "$IDENTITY" ]]; then
    IDENTITIES="$({
        security find-identity -v -p codesigning 2>/dev/null || true
    } | sed -nE         's/^[[:space:]]*[0-9]+\) [0-9A-F]+ "(Developer ID Application:.*)"$/\1/p'
    )"

    COUNT="$(
        printf '%s\n' "$IDENTITIES"             | sed '/^$/d'             | wc -l             | tr -d ' '
    )"

    if [[ "$COUNT" == "1" ]]; then
        IDENTITY="$IDENTITIES"
    elif [[ "$COUNT" == "0" ]]; then
        fail "no usable Developer ID Application identity found in Keychain"
    else
        printf 'Developer ID Application identities found:\n%s\n\n' "$IDENTITIES"
        printf 'Paste the exact identity to use: '
        IFS= read -r IDENTITY </dev/tty
    fi
fi

[[ "$IDENTITY" == Developer\ ID\ Application:* ]]     || fail "identity must start with 'Developer ID Application:'"

TEAM_ID="${WAM_TEAM_ID:-}"
if [[ -z "$TEAM_ID" ]]; then
    TEAM_ID="$(
        printf '%s' "$IDENTITY"             | sed -nE 's/.*\(([A-Z0-9]{10})\)$/\1/p'
    )"
fi

if [[ -z "$TEAM_ID" ]]; then
    printf 'Apple Team ID: '
    IFS= read -r TEAM_ID </dev/tty
fi

[[ "$TEAM_ID" =~ ^[A-Z0-9]{10}$ ]]     || fail "invalid Apple Team ID"

P12_PATH="${WAM_P12_PATH:-}"
if [[ -z "$P12_PATH" ]]; then
    printf 'Path to exported Developer ID .p12: '
    IFS= read -r P12_PATH </dev/tty
fi

P12_PATH="${P12_PATH/#\~/$HOME}"
[[ -f "$P12_PATH" ]]     || fail "P12 file not found: $P12_PATH"

P12_PASSWORD="${WAM_P12_PASSWORD:-}"
if [[ -z "$P12_PASSWORD" ]]; then
    printf 'P12 password (input hidden): '
    IFS= read -r -s P12_PASSWORD </dev/tty
    printf '\n'
fi

[[ -n "$P12_PASSWORD" ]]     || fail "P12 password cannot be empty"

P12_PASSWORD="$P12_PASSWORD" openssl pkcs12     -in "$P12_PATH"     -passin env:P12_PASSWORD     -noout >/dev/null 2>&1     || fail "P12 cannot be opened with the supplied password"

P8_PATH="${WAM_P8_PATH:-}"
if [[ -z "$P8_PATH" ]]; then
    printf 'Path to App Store Connect AuthKey_*.p8: '
    IFS= read -r P8_PATH </dev/tty
fi

P8_PATH="${P8_PATH/#\~/$HOME}"
[[ -f "$P8_PATH" ]]     || fail "P8 file not found: $P8_PATH"

grep -q '^-----BEGIN PRIVATE KEY-----$' "$P8_PATH"     || fail "P8 does not look like an App Store Connect API private key"

API_KEY_ID="${WAM_API_KEY_ID:-}"
if [[ -z "$API_KEY_ID" ]]; then
    BASENAME="$(basename "$P8_PATH")"

    if [[ "$BASENAME" =~ ^AuthKey_([A-Z0-9]+)\.p8$ ]]; then
        API_KEY_ID="${BASH_REMATCH[1]}"
    else
        printf 'App Store Connect API Key ID: '
        IFS= read -r API_KEY_ID </dev/tty
    fi
fi

[[ "$API_KEY_ID" =~ ^[A-Z0-9]+$ ]]     || fail "invalid API key ID"

API_ISSUER_ID="${WAM_API_ISSUER_ID:-}"
if [[ -z "$API_ISSUER_ID" ]]; then
    printf 'App Store Connect API Issuer ID (UUID): '
    IFS= read -r API_ISSUER_ID </dev/tty
fi

[[ "$API_ISSUER_ID" =~ ^[0-9a-fA-F-]{36}$ ]]     || fail "invalid API issuer ID"

printf '\nRepository: %s\n' "$REPO"
printf 'Identity:   %s\n' "$IDENTITY"
printf 'Team ID:    %s\n' "$TEAM_ID"
printf 'API Key ID: %s\n' "$API_KEY_ID"
printf 'Issuer ID:  %s\n\n' "$API_ISSUER_ID"
printf 'Uploading encrypted GitHub Actions secrets...\n'

set_secret_b64_file MACOS_CERTIFICATE_P12_BASE64 "$P12_PATH"
set_secret_text MACOS_CERTIFICATE_PASSWORD "$P12_PASSWORD"
set_secret_text MACOS_SIGNING_IDENTITY "$IDENTITY"
set_secret_text APPLE_TEAM_ID "$TEAM_ID"
set_secret_b64_file APPLE_API_KEY_P8_BASE64 "$P8_PATH"
set_secret_text APPLE_API_KEY_ID "$API_KEY_ID"
set_secret_text APPLE_API_ISSUER_ID "$API_ISSUER_ID"

unset P12_PASSWORD

printf '\nConfigured secret names:\n'
gh secret list --repo "$REPO"     | grep -E         '^(MACOS_CERTIFICATE_P12_BASE64|MACOS_CERTIFICATE_PASSWORD|MACOS_SIGNING_IDENTITY|APPLE_TEAM_ID|APPLE_API_KEY_P8_BASE64|APPLE_API_KEY_ID|APPLE_API_ISSUER_ID)[[:space:]]'     || true

printf '\nMACOS RELEASE CREDENTIAL SETUP: PASS\n'

if [[ "${WAM_NO_DISPATCH:-0}" == "1" ]]; then
    printf 'Workflow dispatch skipped because WAM_NO_DISPATCH=1.\n'
    exit 0
fi

RELEASE_BRANCH="feat/6n7h-macos-signing-notarization"
WORKFLOW="macos-release.yml"

printf '\nDispatching %s on %s...\n' "$WORKFLOW" "$RELEASE_BRANCH"

gh workflow run "$WORKFLOW" \
    --repo "$REPO" \
    --ref "$RELEASE_BRANCH"

RUN_ID=""
for _ in {1..20}; do
    RUN_ID="$(
        gh run list \
            --repo "$REPO" \
            --workflow "$WORKFLOW" \
            --branch "$RELEASE_BRANCH" \
            --event workflow_dispatch \
            --limit 1 \
            --json databaseId \
            --jq '.[0].databaseId // empty'
    )"

    if [[ -n "$RUN_ID" ]]; then
        break
    fi

    sleep 3
done

[[ -n "$RUN_ID" ]] \
    || fail "workflow dispatched but run ID was not discovered"

printf 'Watching GitHub Actions run: %s\n\n' "$RUN_ID"

gh run watch "$RUN_ID" \
    --repo "$REPO" \
    --exit-status

printf '\n6N-7H MACOS SIGNING / NOTARIZATION: PASS\n'
