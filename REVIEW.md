# Technical Review Request

The current desktop/regtest milestone is functionally complete. Independent review is requested before any production or mainnet claim.

This is not a request to rebuild the project. The goal is to find incorrect assumptions, integration mistakes, security weaknesses, missing validation and WAM-specific adoption requirements.

## Repositories

- Desktop wallet: https://github.com/Urriki1502/wam-silent-wallet
- WSP-1 / BIP-352: https://github.com/Urriki1502/wam-silent-payments
- WAM Core: https://github.com/wamcoin-core-dev/wam-coin

## Priority areas

### BIP-352 / WSP-1
Review sender input aggregation, tagged hashes, shared-secret derivation, scan/spend separation, labels, repeated recipients, eligible inputs, Taproot input handling, NUMS handling, x-only output derivation, receiver matching, spending-key derivation and scanner work limits.

Key questions:
- Are Bitcoin BIP-352 assumptions valid for WAM?
- Are there WAM-specific consensus/policy differences?
- What namespace/profile should WAM adopt for mainnet/testnet?

### Signing / transactions
Review coin selection/reservation, PSBTv2, P2TR signing, fee/change invariants, Silent Payment change, UTXO verification, mempool policy checks, broadcast and failure paths.

### Scanner
Review block sync, mempool snapshots, payment detection, restart/resume, atomic commits, rollback/reorg handling, spent-state tracking and balance accounting.

### Key custody / session
Review encrypted `keys.wsp`, Keyring lifecycle, passphrase handling, lock/unlock behavior and accidental key exposure. Known limitation: Python cannot guarantee hardened memory or complete zeroization.

### Backup / recovery
Review authenticated bundles, descriptors/labels/metadata, file permissions, wrong-passphrase behavior, disposable recovery verification and post-restore rescan assumptions.

### WAM Core integration
Current profile:

```text
WAM Core v0.1.11
REGTEST
RPC 127.0.0.1:18443
cookie authentication
```

Review SDK/RPC assumptions, chain attestation, parsing, mempool policy calls, relay behavior and regtest-to-mainnet differences.

## Evidence exercised

```text
wallet load
 -> Silent address
 -> construct
 -> sign
 -> testmempoolaccept
 -> broadcast
 -> confirm
 -> receiver scan
 -> payment detection
 -> balance/history
 -> spend
```

This is regtest evidence, not an independent audit.

## Preferred review outcome

```text
PASS
NEEDS CHANGE
NEEDS SPEC DECISION
NEEDS WAM CORE CHANGE
NEEDS SECURITY REVIEW
OUT OF SCOPE
```

Concrete issues, failing test cases and pull requests are preferred over broad approval.
