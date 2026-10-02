# Contributing

Contributions are welcome, especially focused technical review.

## Priorities

1. correctness
2. security
3. deterministic recovery
4. scanner correctness
5. WAM Core compatibility
6. reviewability
7. UI polish

## Scope

Desktop/application changes belong here.

Changes to BIP-352 derivation, cryptography, scanner internals, PSBT/signing internals or recovery primitives should normally be made in:

https://github.com/Urriki1502/wam-silent-payments

## Pull requests

Please state what problem is fixed, which layer changes, whether wallet state/signing/RPC behavior changes, how it was tested and whether recovery compatibility changes.

Use isolated WAM regtest environments only. Never include real keys or wallet backups in fixtures.
