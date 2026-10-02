# WAM Silent Wallet

Experimental desktop wallet for **WAM Silent Payments**.

> **Status:** Experimental / REGTEST ONLY  
> **Version:** 0.1.0  
> **Validated node:** WAM Core v0.1.11 (regtest)  
> **Protocol engine:** WSP-1 / BIP-352  
> **Mainnet:** Not ready; maintainer review and independent validation are required.

## Architecture

```text
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
```

The protocol engine is intentionally separate:
- WSP-1 / BIP-352: https://github.com/Urriki1502/wam-silent-payments
- WAM Core: https://github.com/wamcoin-core-dev/wam-coin

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Current capabilities

- Python 3.12 + PySide6 / Qt 6 desktop UI
- wallet lock/unlock session
- dashboard, Receive, Send, Payments, Node and Backup views
- Silent Payment base and labeled addresses
- BIP-352 sender/receiver integration through `wam_sp`
- coin selection and reservation
- PSBTv2 / P2TR signing path
- UTXO verification, `testmempoolaccept`, broadcast and confirmation tracking
- durable blockchain scanner and SQLite-backed wallet state
- mempool-aware scanning, rollback/reorg handling and wallet accounting
- encrypted key storage and authenticated recovery bundles
- recovery verification in a disposable database
- WAM SDK / local WAM Core RPC integration
- macOS ARM64 `.app` packaging with PyInstaller

## End-to-end regtest evidence

```text
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
```

This is a real local WAM regtest flow, not a mocked GUI flow.

## Repository structure

```text
wam-silent-wallet/
├── app.py
├── pyproject.toml
├── README.md
├── REVIEW.md
├── SECURITY.md
├── CONTRIBUTING.md
├── docs/
│   ├── ARCHITECTURE.md
│   └── DEVELOPMENT.md
├── scripts/
│   ├── bootstrap_dev.sh
│   └── regtest_send_silent.py
└── src/wam_silent_wallet/
    ├── main_window.py
    ├── theme.py
    ├── ui_components.py
    ├── pages/
    └── services/
```

## Development

Recommended sibling layout:

```text
workspace/
├── wam-silent-wallet/
└── wam-silent-payments/
    └── integration-deps/wam-sdk/
```

Then:

```bash
./scripts/bootstrap_dev.sh
source .venv/bin/activate
python app.py
```

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Review requested

The current application milestone is complete for local regtest use. The next step is independent review of:
- BIP-352/WSP-1 assumptions
- scanner correctness
- signing and accounting
- backup/recovery
- WAM Core integration
- regtest-to-mainnet requirements

See [REVIEW.md](REVIEW.md).

## Important limitations

- regtest-only validated profile
- `wamrtsp` is an experimental regtest namespace
- WAM mainnet/testnet Silent Payments profile still needs maintainer adoption
- external security review/audit is pending
- Python cannot guarantee hardened secret-memory zeroization
- local validating WAM node is trusted for consensus/prevout data
- current macOS build is ARM64, ad-hoc signed and not notarized

## Sensitive files

Never commit or publish:

```text
wallet.db
keys.wsp
.cookie
*.wspbak
wallet passphrases
seed/private-key material
```

See [SECURITY.md](SECURITY.md).

## License

MIT.
