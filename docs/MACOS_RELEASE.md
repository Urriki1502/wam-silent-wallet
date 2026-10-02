# macOS Release Signing and Notarization

This gate turns the reproducible PyInstaller app from the 6N-7G integrity
pipeline into a distributable Developer ID signed and Apple-notarized DMG.

## Security contract

The release workflow requires:

- a valid **Developer ID Application** certificate exported as PKCS#12;
- the PKCS#12 password;
- the exact Developer ID signing identity;
- the Apple Developer Team ID;
- an App Store Connect / notarization API private key;
- the API key ID and issuer ID.

The workflow imports the signing certificate into an ephemeral keychain,
materializes the notarization key only under the GitHub runner temporary
directory, and deletes both in the final cleanup step.

The application bundle identifier is fixed to:

`org.wamcoin.silentwallet`

The entitlements file is intentionally empty. Hardened Runtime is enabled
by PyInstaller when a real code-signing identity is supplied. Do not add
runtime exception entitlements unless a concrete application feature
requires one and that exception has been separately reviewed.

## GitHub Actions secrets

Configure these repository or environment secrets before running
`macOS Release Signing & Notarization`:

- `MACOS_CERTIFICATE_P12_BASE64`
- `MACOS_CERTIFICATE_PASSWORD`
- `MACOS_SIGNING_IDENTITY`
- `APPLE_TEAM_ID`
- `APPLE_API_KEY_P8_BASE64`
- `APPLE_API_KEY_ID`
- `APPLE_API_ISSUER_ID`

Encode the binary PKCS#12 file and the P8 private key as standard Base64
without changing their original bytes.

## Qualification sequence

The workflow performs the following release gates in order:

1. validate the credential contract;
2. import the Developer ID certificate into an ephemeral keychain;
3. install the exact hash-locked Python dependencies and pinned WSP source;
4. rerun supply-chain, artifact, contamination, regression, and test gates;
5. build the app using the Developer ID identity and Hardened Runtime;
6. reject ad-hoc signatures, a wrong bundle ID, a wrong Team ID, a missing
   Developer ID authority, a missing Hardened Runtime flag, or a missing
   secure timestamp;
7. create and Developer ID sign the DMG;
8. submit the DMG with `notarytool` and require status `Accepted`;
9. staple the notarization ticket and validate it;
10. run Gatekeeper assessment on the stapled DMG;
11. emit machine-readable release qualification evidence and upload the
    DMG plus evidence as a GitHub Actions artifact.

A successful workflow is the 6N-7H release-engineering gate. It does not
remove the wallet's Regtest-only safety boundary and does not qualify the
protocol or wallet for real-money mainnet use.
