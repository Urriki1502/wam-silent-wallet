# WAM Silent Wallet

Experimental desktop wallet for **WAM Silent Payments**.

> **Status:** Experimental / REGTEST ONLY  
> **Version:** 0.1.0  
> **Validated node:** WAM Core v0.1.11 (regtest)  
> **Protocol engine:** WSP-1 / BIP-352  
> **Mainnet:** Not ready; maintainer review and independent validation are required.

## Architecture

    WAM Silent Wallet (PySide6 / Qt)
            |
            +-- SessionService
            +-- WalletService ---> WSP-1 / BIP-352
            |                        +-- secp256k1
            |                        +-- scanner/accounting
            |                        +-- PSBTv2 / P2TR signing
            |                        +-- backup/recovery
            |
            +-- NodeService -----> WAM SDK -----> WAM Core

The protocol engine is intentionally separate:
- WSP-1 / BIP-352: https://github.com/Urriki1502/wam-silent-payments
- WAM Core: https://github.com/wamcoin-core-dev/wam-coin

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Current capabilities

- Python 3.12 + PySide6 / Qt 6 desktop UI
- wallet lock/unlock session
- dashboard, Receive, Send, Payments, Node and Backup views
- Silent Payment base and labeled addresses
- BIP-352 sender/receiver integration through \`wam_sp\`
- coin selection and reservation
- PSBTv2 / P2TR signing path
- UTXO verification, \`testmempoolaccept\`, broadcast and confirmation tracking
- durable blockchain scanner and SQLite-backed wallet state
- mempool-aware scanning, rollback/reorg handling and wallet accounting
- encrypted key storage and authenticated recovery bundles
- recovery verification in a disposable database
- WAM SDK / local WAM Core RPC integration
- macOS ARM64 \`.app\` packaging with PyInstaller
- reproducible app-content qualification
- hash-locked supply-chain inputs and CycloneDX SBOM
- macOS ZIP/DMG release packaging
- Developer ID / Hardened Runtime / Apple notarization pipeline when release credentials are configured

## End-to-end regtest evidence

    Silent address
     -> construct payment
     -> BIP-352 derivation
     -> sign
     -> mempool policy check
     -> broadcast
     -> confirmation
     -> receiver scan
     -> payment detection
     -> balance/history update
     -> spend

This is a real local WAM regtest flow, not a mocked GUI flow.

## Development

Recommended sibling layout:

    workspace/
    ├── wam-silent-wallet/
    └── wam-silent-payments/
        └── integration-deps/wam-sdk/

Then:

    ./scripts/bootstrap_dev.sh
    source .venv/bin/activate
    python app.py

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Release engineering

Release qualification includes locked dependencies, SBOM verification,
full regression, release contamination scanning, independent reproducible
app builds, clean-home packaged launch testing, release manifests and
checksums.

For public macOS distribution, the release workflow also supports Apple
Developer ID signing, Hardened Runtime, \`notarytool\` submission, stapling
and Gatekeeper assessment.

See [docs/RELEASE.md](docs/RELEASE.md).

## Review requested

The current application milestone is complete for local regtest use. The next
step is independent review of:

- BIP-352/WSP-1 assumptions
- scanner correctness
- signing and accounting
- backup/recovery
- WAM Core integration
- regtest-to-mainnet requirements

See [REVIEW.md](REVIEW.md).

## Important limitations

- regtest-only validated profile
- \`wamrtsp\` is an experimental regtest namespace
- WAM mainnet/testnet Silent Payments profile still needs maintainer adoption
- external security review/audit is pending
- Python cannot guarantee hardened secret-memory zeroization
- local validating WAM node is trusted for consensus/prevout data
- public macOS distribution requires configured Developer ID and notarization credentials

## Sensitive files

Never commit or publish:

    wallet.db
    keys.wsp
    .cookie
    *.wspbak
    wallet passphrases
    seed/private-key material

See [SECURITY.md](SECURITY.md).

## License

MIT.
