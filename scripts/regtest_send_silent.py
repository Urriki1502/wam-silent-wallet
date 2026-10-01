#!/usr/bin/env python3

"""
WAM Silent Wallet v0.1
REGTEST-ONLY end-to-end Silent Payment sender.

This script:
1. unlocks the local demo Silent Wallet only to obtain its public payment code;
2. creates a disposable synthetic sender key;
3. mines mature regtest funds to that sender;
4. derives a real WSP-1/BIP-352 output;
5. signs and broadcasts the transaction;
6. mines one confirmation block.

NEVER use this helper against mainnet.
"""

import json
import secrets
import subprocess
from getpass import getpass
from pathlib import Path

from wam_sp.codec import encode
from wam_sp.core import Input, N, pub, send
from wam_sp.scanner import atoms
from wam_sp.transaction import p2wpkh, signed_single_input

from wam_silent_wallet.services.wallet_service import WalletService


HOME = Path.home()

WAMCLI = HOME / "wam" / "wam-coin-v0.1.11" / "bin" / "wam-cli"
DATADIR = HOME / "wam" / "regtest-silent-wallet"
CONF = DATADIR / "wam.conf"

PAYMENT_ATOMS = 100_000_000   # 1.00000000 WAM
FEE_ATOMS = 1_000             # 0.00001000 WAM


def cli(method, *params):
    cmd = [
        str(WAMCLI),
        "-regtest",
        f"-datadir={DATADIR}",
        f"-conf={CONF}",
        method,
    ]

    for value in params:
        if isinstance(value, (list, dict)):
            cmd.append(json.dumps(value, separators=(",", ":")))
        else:
            cmd.append(str(value))

    result = subprocess.run(
        cmd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    output = result.stdout.strip()

    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return output


def main():
    # ------------------------------------------------------------
    # Safety checks
    # ------------------------------------------------------------

    if not WAMCLI.is_file():
        raise SystemExit("WAM CLI v0.1.11 not found.")

    info = cli("getblockchaininfo")

    if info.get("chain") != "regtest":
        raise SystemExit("REFUSING: node is not WAM regtest.")

    if cli("getconnectioncount") != 0:
        raise SystemExit(
            "REFUSING: demo node unexpectedly has external peers."
        )

    # ------------------------------------------------------------
    # Obtain recipient Silent Payment code
    # ------------------------------------------------------------

    password = getpass("Demo Silent Wallet passphrase: ")

    wallet_service = WalletService()

    silent_address = wallet_service.receive_address(password)

    # Do not retain passphrase any longer than necessary.
    password = None

    print()
    print("Recipient WSP address:")
    print(silent_address)
    print()

    # ------------------------------------------------------------
    # Create disposable sender
    # ------------------------------------------------------------

    sender_secret = secrets.randbelow(N - 1) + 1

    sender_script = p2wpkh(sender_secret)

    # WAM regtest native SegWit v0 address.
    sender_address = encode(
        "wamrt",
        sender_script[2:],
        0,
        bech32m=False,
    )

    print("Creating disposable REGTEST sender...")
    print("Mining 110 blocks for mature test funds...")

    blocks = cli(
        "generatetoaddress",
        110,
        sender_address,
    )

    if not isinstance(blocks, list) or len(blocks) != 110:
        raise RuntimeError("Unexpected mining result.")

    # ------------------------------------------------------------
    # Select the first coinbase from this mining run
    # ------------------------------------------------------------

    first_block = cli(
        "getblock",
        blocks[0],
        2,
    )

    coinbase = first_block["tx"][0]

    coin = next(
        output
        for output in coinbase["vout"]
        if output["scriptPubKey"]["hex"] == sender_script.hex()
    )

    input_amount = atoms(coin["value"])

    if input_amount <= PAYMENT_ATOMS + FEE_ATOMS:
        raise RuntimeError("Coinbase value too small.")

    txin = Input(
        coinbase["txid"],
        coin["n"],
        sender_script,
        witness=(b"", pub(sender_secret)),
        secret=sender_secret,
    )

    # ------------------------------------------------------------
    # WSP-1 derivation
    # ------------------------------------------------------------

    (silent_output,) = send(
        [txin],
        [silent_address],
    )

    silent_script = b"\x51\x20" + silent_output

    change_atoms = (
        input_amount
        - PAYMENT_ATOMS
        - FEE_ATOMS
    )

    # ------------------------------------------------------------
    # Build + sign real transaction
    # ------------------------------------------------------------

    raw_tx = signed_single_input(
        txin,
        input_amount,
        [
            (
                PAYMENT_ATOMS,
                silent_script,
            ),
            (
                change_atoms,
                sender_script,
            ),
        ],
        sender_secret,
    )

    # ------------------------------------------------------------
    # Mempool policy check
    # ------------------------------------------------------------

    acceptance = cli(
        "testmempoolaccept",
        [raw_tx],
    )

    if (
        not isinstance(acceptance, list)
        or not acceptance
        or not acceptance[0].get("allowed")
    ):
        raise RuntimeError(
            "WAM Core rejected the Silent Payment transaction."
        )

    print("Mempool policy check: PASS")

    # ------------------------------------------------------------
    # Broadcast
    # ------------------------------------------------------------

    txid = cli(
        "sendrawtransaction",
        raw_tx,
    )

    print("Broadcast: PASS")
    print("TXID:", txid)

    # ------------------------------------------------------------
    # Confirm payment
    # ------------------------------------------------------------

    confirmation = cli(
        "generatetoaddress",
        1,
        sender_address,
    )

    if not isinstance(confirmation, list) or len(confirmation) != 1:
        raise RuntimeError("Confirmation block was not generated.")

    height = cli("getblockcount")

    print("Confirmation: PASS")
    print("Chain height:", height)
    print()
    print("Silent Payment sent: 1.00000000 WAM")
    print("Now scan the wallet from the GUI.")


if __name__ == "__main__":
    main()
