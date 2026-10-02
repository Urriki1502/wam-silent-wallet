# Architecture

```mermaid
flowchart TB
  U[Wallet User] --> UI[PySide6 / Qt UI]
  UI --> MW[MainWindow]
  MW --> S[SessionService]
  MW --> W[WalletService]
  MW --> N[NodeService]

  W --> API[WSP-1 SilentWallet API]
  W --> K[Keyring]
  W --> SG[Signer]
  W --> R[Recovery]
  API --> SC[Scanner]
  API --> A[Wallet Accounting]
  SC --> B[BIP-352]
  SG --> B
  SG --> P[PSBTv2 / P2TR]
  SC --> DB[(SQLite)]
  A --> DB

  N --> SDK[WAM SDK / WamClient]
  N --> AD[SDKChain Adapter]
  AD --> SDK
  SDK --> RPC[WAM Core JSON-RPC]
  RPC --> M[Mempool Policy]
  RPC --> C[Regtest Chain]
```

## Repository boundaries

### `wam-silent-wallet`
Owns UI, app lifecycle, session handling, wallet/node orchestration, packaging and regtest UX.

### `wam-silent-payments`
Owns BIP-352 derivation, secp256k1 operations, scanner, accounting, signing, PSBT, descriptors, recovery primitives, SQLite state and chain adapters.

### WAM SDK
Owns RPC configuration, cookie authentication and WAM Core client access.

### WAM Core
Owns consensus, UTXO/chain state, mempool policy, relay and confirmation.

## Send flow

```mermaid
sequenceDiagram
  participant UI as Send UI
  participant WS as WalletService
  participant WSP as WSP Wallet
  participant SG as Signer
  participant N as WAM Core

  UI->>WS: destination + amount
  WS->>WSP: scan current state
  WSP->>WSP: select/reserve coins
  WSP->>WSP: construct Silent Payment
  WS->>SG: prepare/sign
  SG-->>WS: signed PSBT
  WS->>N: verify UTXOs
  WS->>N: testmempoolaccept
  WS->>N: sendrawtransaction
  N-->>WS: txid
  WS-->>UI: result
```

## Node profile

```text
RPC: http://127.0.0.1:18443
Cookie: ~/wam/regtest-silent-wallet/regtest/.cookie
Network: REGTEST
```

## Recovery model

```text
encrypted recovery bundle
 -> keyring + descriptors + metadata
 -> fresh wallet database
 -> validating WAM node rescan
 -> recovered wallet state
```

Recovery verification uses a disposable database and does not overwrite the active wallet.

## Security boundary

Current assumptions:
1. host OS is not hostile;
2. local validating WAM node is trusted for consensus and prevout data;
3. encrypted wallet files are protected by the passphrase;
4. Python memory is not hardened native secret memory.
