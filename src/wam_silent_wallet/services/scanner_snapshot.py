"""Application boundary for verified WSP scanner snapshots.

The protocol scanner owns chain verification.  This module validates and
normalizes the scanner state before it is allowed to cross into the desktop
wallet/UI layer.
"""

from __future__ import annotations

import hashlib
import json
import re


_TXID = re.compile(r"^[0-9a-f]{64}$")


def _integer(
    value,
    minimum,
    maximum,
    code,
):
    if (
        type(value) is not int
        or not minimum <= value <= maximum
    ):
        raise ValueError(code)

    return value


def _txid(
    value,
):
    if (
        not isinstance(value, str)
        or _TXID.fullmatch(value) is None
    ):
        raise ValueError(
            "SCANNER_TXID"
        )

    return value


def _label_metadata(
    wallet,
):
    scanner = wallet.scanner

    epochs = {}

    for account in scanner.accounts:
        if account.epoch in epochs:
            raise ValueError(
                "SCANNER_EPOCH_DUPLICATE"
            )

        epochs[account.epoch] = (
            account.account_id
        )

    labels = {}

    for row in scanner.store.db.execute(
        """
        SELECT account,label,name
        FROM labels
        """
    ):
        key = (
            row["account"],
            row["label"],
        )

        if key in labels:
            raise ValueError(
                "SCANNER_LABEL_DUPLICATE"
            )

        labels[key] = row["name"]

    return epochs, labels


def _payment_rows(
    wallet,
    tip_height: int,
):
    db = wallet.scanner.store.db

    visible_count = db.execute(
        """
        SELECT COUNT(*)
        FROM coins
        WHERE label IS NULL
           OR label<>0
        """
    ).fetchone()[0]

    _integer(
        visible_count,
        0,
        1_000_000,
        "SCANNER_PAYMENT_LIMIT",
    )

    reserved_label_zero = db.execute(
        """
        SELECT COUNT(*)
        FROM coins
        WHERE label=0
        """
    ).fetchone()[0]

    _integer(
        reserved_label_zero,
        0,
        1_000_000,
        "SCANNER_PAYMENT_LIMIT",
    )

    # Filter reserved label-0 rows BEFORE pagination.
    # This avoids offset drift when protocol-reserved outputs
    # exist among otherwise visible wallet payments.
    rows = db.execute(
        """
        SELECT
            txid,
            vout,
            atoms,
            label,
            epoch,
            received,
            spent
        FROM coins
        WHERE label IS NULL
           OR label<>0
        ORDER BY
            received DESC,
            txid DESC,
            vout DESC
        LIMIT 1000
        """
    ).fetchall()

    normalized = []

    for row in rows:
        item = dict(row)

        item["confirmations"] = (
            tip_height
            - item["received"]
            + 1
        )

        normalized.append(
            item
        )

    return (
        visible_count,
        reserved_label_zero,
        normalized,
    )


def _mempool_state(
    wallet,
    epochs,
    labels,
):
    db = wallet.scanner.store.db

    received_rows = list(
        db.execute(
            """
            SELECT
                txid,
                vout,
                account,
                epoch,
                atoms,
                label
            FROM mempool_coins
            ORDER BY txid,vout
            """
        )
    )

    spend_rows = list(
        db.execute(
            """
            SELECT
                txid,
                vout,
                spending
            FROM mempool_spends
            ORDER BY txid,vout
            """
        )
    )

    if (
        len(received_rows) > 10_000
        or len(spend_rows) > 10_000
    ):
        raise ValueError(
            "SCANNER_MEMPOOL_LIMIT"
        )

    received = []

    for row in received_rows:
        txid = _txid(
            row["txid"]
        )

        vout = _integer(
            row["vout"],
            0,
            2**32 - 1,
            "SCANNER_MEMPOOL_VOUT",
        )

        epoch = _integer(
            row["epoch"],
            0,
            2**31 - 1,
            "SCANNER_MEMPOOL_EPOCH",
        )

        atoms = _integer(
            row["atoms"],
            0,
            22_000_000
            * 100_000_000,
            "SCANNER_MEMPOOL_AMOUNT",
        )

        if (
            epoch not in epochs
            or epochs[epoch]
            != row["account"]
        ):
            raise ValueError(
                "SCANNER_MEMPOOL_ACCOUNT"
            )

        label = row["label"]

        if label is not None:
            _integer(
                label,
                0,
                2**32 - 1,
                "SCANNER_MEMPOOL_LABEL",
            )

            if (
                label != 0
                and (
                    row["account"],
                    label,
                ) not in labels
            ):
                raise ValueError(
                    "SCANNER_LABEL_METADATA_MISSING"
                )

        received.append(
            {
                "txid": txid,
                "vout": vout,
                "atoms": atoms,
                "epoch": epoch,
                "label": label,
            }
        )

    spent = []

    for row in spend_rows:
        txid = _txid(
            row["txid"]
        )

        spending = _txid(
            row["spending"]
        )

        vout = _integer(
            row["vout"],
            0,
            2**32 - 1,
            "SCANNER_MEMPOOL_VOUT",
        )

        spent.append(
            {
                "txid": txid,
                "vout": vout,
                "spending": spending,
            }
        )

    return received, spent


def build_scanner_snapshot(
    wallet,
    metrics,
) -> dict:
    scanner = wallet.scanner

    # Protocol scanner must prove chain currency first.
    scanner.assert_current()

    if not scanner.mempool_ready:
        raise ValueError(
            "MEMPOOL_NOT_CURRENT"
        )

    tip = scanner.store.tip()

    if (
        scanner.verified_tip != tip
        or type(tip[0]) is not int
        or tip[0] < 0
        or not isinstance(tip[1], str)
        or _TXID.fullmatch(tip[1]) is None
    ):
        raise ValueError(
            "SCANNER_TIP_INVALID"
        )

    tip_height, tip_hash = tip

    balance = wallet.get_balance()

    for field in (
        "confirmed_atoms",
        "available_atoms",
        "reserved_atoms",
        "unconfirmed_atoms",
        "pending_spent_atoms",
    ):
        value = balance.get(field)

        if value is None:
            raise ValueError(
                "SCANNER_BALANCE_INCOMPLETE"
            )

        _integer(
            value,
            0,
            22_000_000
            * 100_000_000,
            "SCANNER_BALANCE_INVALID",
        )

    if (
        balance["available_atoms"]
        > balance["confirmed_atoms"]
    ):
        raise ValueError(
            "SCANNER_BALANCE_INVALID"
        )

    epochs, labels = (
        _label_metadata(
            wallet
        )
    )

    (
        visible_count,
        reserved_label_zero,
        raw_payments,
    ) = _payment_rows(
        wallet,
        tip_height,
    )

    payments = []
    seen_outpoints = set()
    for item in raw_payments:
        txid = _txid(
            item.get("txid")
        )

        vout = _integer(
            item.get("vout"),
            0,
            2**32 - 1,
            "SCANNER_VOUT",
        )

        outpoint = (
            txid,
            vout,
        )

        if outpoint in seen_outpoints:
            raise ValueError(
                "SCANNER_DUPLICATE_OUTPOINT"
            )

        seen_outpoints.add(
            outpoint
        )

        atoms = _integer(
            item.get("atoms"),
            0,
            22_000_000
            * 100_000_000,
            "SCANNER_PAYMENT_AMOUNT",
        )

        epoch = _integer(
            item.get("epoch"),
            0,
            2**31 - 1,
            "SCANNER_PAYMENT_EPOCH",
        )

        if epoch not in epochs:
            raise ValueError(
                "SCANNER_PAYMENT_EPOCH"
            )

        received = _integer(
            item.get("received"),
            1,
            tip_height,
            "SCANNER_PAYMENT_HEIGHT",
        )

        confirmations = _integer(
            item.get("confirmations"),
            1,
            tip_height + 1,
            "SCANNER_CONFIRMATIONS",
        )

        expected_confirmations = (
            tip_height
            - received
            + 1
        )

        if (
            confirmations
            != expected_confirmations
        ):
            raise ValueError(
                "SCANNER_CONFIRMATION_MISMATCH"
            )

        spent = item.get(
            "spent"
        )

        if spent is not None:
            _integer(
                spent,
                received,
                tip_height,
                "SCANNER_SPENT_HEIGHT",
            )

        label = item.get(
            "label"
        )

        # Reserved label 0 was removed at the SQL boundary
        # before pagination, therefore it must never reach UI
        # normalization.
        if label == 0:
            raise ValueError(
                "SCANNER_RESERVED_LABEL_LEAK"
            )

        if label is None:
            label_name = "Base"

        else:
            _integer(
                label,
                1,
                2**32 - 1,
                "SCANNER_LABEL",
            )

            account_id = epochs[
                epoch
            ]

            key = (
                account_id,
                label,
            )

            if key not in labels:
                raise ValueError(
                    "SCANNER_LABEL_METADATA_MISSING"
                )

            label_name = labels[
                key
            ]

        payments.append(
            {
                "txid": txid,
                "vout": vout,
                "atoms": atoms,
                "amount_wam": (
                    atoms
                    / 100_000_000
                ),
                "label": label,
                "label_name": (
                    label_name
                ),
                "epoch": epoch,
                "received": received,
                "spent": spent,
                "confirmations": (
                    confirmations
                ),
            }
        )

    # The DB count excludes reserved label zero, therefore it must
    # equal the normalized visible collection when <=1000.
    if (
        visible_count <= 1000
        and len(payments)
        != visible_count
    ):
        raise ValueError(
            "SCANNER_PAYMENT_COUNT_MISMATCH"
        )

    history_count = (
        scanner.store.db.execute(
            """
            SELECT COUNT(*)
            FROM history
            """
        ).fetchone()[0]
    )

    _integer(
        history_count,
        0,
        1_000_000,
        "SCANNER_HISTORY_LIMIT",
    )

    (
        mempool_received,
        mempool_spent,
    ) = _mempool_state(
        wallet,
        epochs,
        labels,
    )

    mempool_coins = len(
        mempool_received
    )

    mempool_spends = len(
        mempool_spent
    )

    stable = {
        "tip": [
            tip_height,
            tip_hash,
        ],
        "balance": {
            key: balance[key]
            for key in sorted(
                balance
            )
        },
        "payments_count": (
            visible_count
        ),
        "payments": [
            {
                key: item[key]
                for key in (
                    "txid",
                    "vout",
                    "atoms",
                    "label",
                    "label_name",
                    "epoch",
                    "received",
                    "spent",
                    "confirmations",
                )
            }
            for item in payments
        ],
        "history_count": (
            history_count
        ),
        "mempool_coins": (
            mempool_coins
        ),
        "mempool_spends": (
            mempool_spends
        ),
        "mempool_received": (
            mempool_received
        ),
        "mempool_spent": (
            mempool_spent
        ),
    }

    fingerprint = hashlib.sha256(
        json.dumps(
            stable,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    return {
        "scanner_tip_height": (
            tip_height
        ),
        "scanner_tip_hash": (
            tip_hash
        ),
        "scanner_current": True,
        "mempool_current": True,
        "snapshot_fingerprint": (
            fingerprint
        ),
        "scan_blocks": (
            metrics.blocks
        ),
        "scan_transactions": (
            metrics.transactions
        ),
        "scan_candidates": (
            metrics.candidates
        ),
        "scan_rollback": (
            metrics.rollback
        ),
        "confirmed_atoms": (
            balance[
                "confirmed_atoms"
            ]
        ),
        "available_atoms": (
            balance[
                "available_atoms"
            ]
        ),
        "reserved_atoms": (
            balance[
                "reserved_atoms"
            ]
        ),
        "unconfirmed_atoms": (
            balance[
                "unconfirmed_atoms"
            ]
        ),
        "pending_spent_atoms": (
            balance[
                "pending_spent_atoms"
            ]
        ),
        "payments_count": (
            visible_count
        ),
        "payments": payments,
        "reserved_label_zero_count": (
            reserved_label_zero
        ),
        "history_count": (
            history_count
        ),
        "mempool_coin_count": (
            mempool_coins
        ),
        "mempool_spend_count": (
            mempool_spends
        ),
        "mempool_received": (
            mempool_received
        ),
        "mempool_spent": (
            mempool_spent
        ),
    }
