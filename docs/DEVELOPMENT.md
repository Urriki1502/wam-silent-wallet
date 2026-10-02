# Development

## Requirements
- Python 3.12+
- Git
- WAM Core v0.1.11
- local WAM regtest node

## Workspace

```text
workspace/
├── wam-silent-wallet/
└── wam-silent-payments/
    └── integration-deps/wam-sdk/
```

## Clone

```bash
git clone https://github.com/Urriki1502/wam-silent-wallet.git
git clone -b feat/wsp1-v1.0 https://github.com/Urriki1502/wam-silent-payments.git
```

## Bootstrap

```bash
./scripts/bootstrap_dev.sh
source .venv/bin/activate
python app.py
```

## Default regtest node

```text
RPC: http://127.0.0.1:18443
Cookie: ~/wam/regtest-silent-wallet/regtest/.cookie
```

## Wallet data

Default macOS demo directory:

```text
~/Library/Application Support/WAM Silent Wallet Demo/
```

Never commit `wallet.db`, `keys.wsp`, `.cookie` or `*.wspbak`.

## Regtest sender helper

`scripts/regtest_send_silent.py` is REGTEST ONLY. It creates a disposable sender, mines mature test funds, derives a WSP-1 output, checks mempool policy, broadcasts and mines a confirmation.

## Packaging

The current macOS build uses PyInstaller, is ARM64, bundles WSP-1 and WAM SDK, excludes wallet/runtime secrets, is ad-hoc signed and is not notarized.

## Before changes are submitted

```bash
python -m compileall -q app.py src
```

Then exercise launch, unlock, node status, receive, scan, payments, backup verification and lock. Transaction changes should also exercise the isolated regtest send/receive flow.
