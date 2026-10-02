# macOS Release Engineering

WAM Silent Wallet remains an experimental **regtest-only** wallet. This
document describes the release-engineering pipeline; it does not authorize
mainnet use.

## Release modes

Two release modes are supported.

### Ad-hoc qualification

Used on feature branches and for local packaging qualification:

    RELEASE_MODE=adhoc \
    RUN_LAUNCH_SMOKE=1 \
    ./scripts/macos_release.sh

This produces an ad-hoc signed ARM64 app, ZIP, DMG, SBOM, lock files,
checksums and a release manifest. It is not suitable for public distribution.

### Developer ID + notarization

Public macOS distribution requires an Apple-issued **Developer ID
Application** certificate, Hardened Runtime, a secure timestamp and Apple
notarization.

    export RELEASE_MODE=developer-id
    export RELEASE_VERSION=0.1.0
    export MACOS_CODESIGN_IDENTITY="Developer ID Application: Example (TEAMID)"
    export APPLE_ID="developer@example.com"
    export APPLE_TEAM_ID="TEAMID"
    export APPLE_APP_PASSWORD="xxxx-xxxx-xxxx-xxxx"

    ./scripts/macos_release.sh

PyInstaller signs collected Mach-O binaries and the app bundle with the
provided identity. When a real identity is supplied, PyInstaller enables
Hardened Runtime. The release script then submits a ZIP to Apple's notary
service with \`notarytool\`, waits for an Accepted result, staples the ticket
to the app, validates Gatekeeper assessment, and creates the final ZIP/DMG.

## GitHub Actions secrets

The \`macos-release.yml\` workflow expects these repository secrets for
Developer ID releases:

- \`MACOS_CERT_P12_BASE64\`: base64-encoded Developer ID Application P12
- \`MACOS_CERT_PASSWORD\`: P12 password
- \`APPLE_ID\`: Apple developer account email used for notarization
- \`APPLE_TEAM_ID\`: Apple Developer Team ID
- \`APPLE_APP_PASSWORD\`: app-specific password for \`notarytool\`

Feature-branch dry runs do not require Apple secrets.

## Release evidence

Each build emits:

- \`WAM-Silent-Wallet-<version>-macOS-arm64.zip\`
- \`WAM-Silent-Wallet-<version>-macOS-arm64.dmg\`
- \`release-manifest.json\`
- \`SHA256SUMS.txt\`
- \`sbom.cdx.json\`
- \`supply-chain.lock.json\`
- \`artifacts.lock.json\`
- \`requirements-hashed.txt\`

The manifest records the Git commit/tree, bundle identity, app-content
fingerprint, release-input hashes and output hashes.

## Tag release

After review and merge to \`main\`, create a version tag:

    git tag -s v0.1.0 -m "WAM Silent Wallet v0.1.0"
    git push origin v0.1.0

A \`v*\` tag forces Developer ID mode. The workflow fails closed if signing
or notarization credentials are unavailable. A successful tag workflow
publishes the generated release evidence as GitHub Release assets.

## Qualification boundary

A green release workflow proves packaging, code-signature structure,
artifact integrity, clean-home launch behavior and, when credentials are
configured, notarization/Gatekeeper acceptance.

It does **not** replace an independent wallet/protocol security review or
authorize moving the application from regtest to mainnet.
