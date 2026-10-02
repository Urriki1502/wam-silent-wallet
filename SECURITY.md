# Security Policy

## Status

WAM Silent Wallet is experimental and REGTEST ONLY. It is not currently intended to secure mainnet funds.

## Sensitive material

Never publish, commit, attach to issues or paste into chat:

```text
wallet.db
keys.wsp
.cookie
*.wspbak
wallet passphrases
seed material
private keys
raw recovery secrets
```

`.gitignore` is only a secondary safeguard.

## Reporting

Do not publicly disclose exploitable wallet, cryptographic, signing, recovery or WAM Core vulnerabilities before maintainers have had an opportunity to review them privately.

Protocol-engine issues: https://github.com/Urriki1502/wam-silent-payments

WAM Core issues: follow the WAM Core project's security process at https://github.com/wamcoin-core-dev/wam-coin

## Current assumptions

- trusted local OS
- trusted validating local WAM node
- passphrase-protected encrypted wallet material
- no protection against a fully compromised host
- no guaranteed constant-time Python bookkeeping
- no guaranteed Python-memory zeroization
- no secure enclave integration

## Mainnet

Do not enable mainnet merely by changing a network constant. Mainnet enablement requires protocol/profile adoption, review and a separate release decision.
