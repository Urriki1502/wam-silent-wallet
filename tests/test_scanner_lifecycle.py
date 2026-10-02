import sqlite3
from types import SimpleNamespace
import unittest

from wam_silent_wallet.services.scanner_snapshot import (
    build_scanner_snapshot,
)


TIP_A = "aa" * 32
TIP_B = "bb" * 32
TIP_C = "cc" * 32


class LifecycleStore:
    def __init__(self):
        self.db = sqlite3.connect(
            ":memory:"
        )

        self.db.row_factory = (
            sqlite3.Row
        )

        self.tip_state = (
            10,
            TIP_A,
        )

        self.db.executescript(
            """
            CREATE TABLE labels(
                account TEXT,
                label INTEGER,
                name TEXT
            );

            CREATE TABLE coins(
                txid TEXT,
                vout INTEGER,
                atoms INTEGER,
                label INTEGER,
                epoch INTEGER,
                received INTEGER,
                spent INTEGER
            );

            CREATE TABLE history(
                txid TEXT
            );

            CREATE TABLE mempool_coins(
                txid TEXT,
                vout INTEGER,
                account TEXT,
                epoch INTEGER,
                atoms INTEGER,
                label INTEGER
            );

            CREATE TABLE mempool_spends(
                txid TEXT,
                vout INTEGER,
                spending TEXT
            );
            """
        )

        self.db.execute(
            """
            INSERT INTO labels
            VALUES(?,?,?)
            """,
            (
                "acct-1",
                1,
                "Invoice 001",
            ),
        )

        self.db.execute(
            """
            INSERT INTO coins
            VALUES(?,?,?,?,?,?,?)
            """,
            (
                "11" * 32,
                0,
                500_000,
                None,
                7,
                9,
                None,
            ),
        )

    def tip(self):
        return self.tip_state


class LifecycleScanner:
    def __init__(self):
        self.store = LifecycleStore()

        self.accounts = (
            SimpleNamespace(
                account_id="acct-1",
                epoch=7,
            ),
        )

        self.ready = True
        self.mempool_ready = True

        self.verified_tip = (
            self.store.tip()
        )

    def assert_current(self):
        if (
            not self.ready
            or self.verified_tip
            != self.store.tip()
        ):
            raise ValueError(
                "SCAN_NOT_CURRENT"
            )

    def set_tip(
        self,
        height,
        block_hash,
    ):
        self.store.tip_state = (
            height,
            block_hash,
        )

        self.verified_tip = (
            self.store.tip()
        )


class LifecycleWallet:
    def __init__(self):
        self.scanner = (
            LifecycleScanner()
        )

    def get_balance(self):
        db = self.scanner.store.db

        confirmed = db.execute(
            """
            SELECT COALESCE(
                SUM(atoms),
                0
            )
            FROM coins
            WHERE spent IS NULL
            """
        ).fetchone()[0]

        unconfirmed = db.execute(
            """
            SELECT COALESCE(
                SUM(atoms),
                0
            )
            FROM mempool_coins
            """
        ).fetchone()[0]

        pending_spent = db.execute(
            """
            SELECT COALESCE(
                SUM(c.atoms),
                0
            )
            FROM coins c
            JOIN mempool_spends m
              ON m.txid=c.txid
             AND m.vout=c.vout
            WHERE c.spent IS NULL
            """
        ).fetchone()[0]

        return {
            "confirmed_atoms": (
                confirmed
            ),
            "reserved_atoms": 0,
            "available_atoms": max(
                0,
                confirmed
                - pending_spent,
            ),
            "unconfirmed_atoms": (
                unconfirmed
            ),
            "pending_spent_atoms": (
                pending_spent
            ),
        }


METRICS = SimpleNamespace(
    blocks=0,
    transactions=0,
    candidates=0,
    rollback=0,
)


class ScannerLifecycleTests(
    unittest.TestCase
):
    def test_confirmation_advance_changes_snapshot(self):
        wallet = LifecycleWallet()

        first = build_scanner_snapshot(
            wallet,
            METRICS,
        )

        self.assertEqual(
            first["payments"][0][
                "confirmations"
            ],
            2,
        )

        wallet.scanner.set_tip(
            11,
            TIP_B,
        )

        second = build_scanner_snapshot(
            wallet,
            METRICS,
        )

        self.assertEqual(
            second["payments"][0][
                "confirmations"
            ],
            3,
        )

        self.assertNotEqual(
            first[
                "snapshot_fingerprint"
            ],
            second[
                "snapshot_fingerprint"
            ],
        )

    def test_reorg_removes_orphaned_payment(self):
        wallet = LifecycleWallet()

        before = build_scanner_snapshot(
            wallet,
            METRICS,
        )

        db = wallet.scanner.store.db

        db.execute(
            """
            DELETE FROM coins
            WHERE received>?
            """,
            (
                8,
            ),
        )

        wallet.scanner.set_tip(
            8,
            TIP_B,
        )

        after = build_scanner_snapshot(
            wallet,
            SimpleNamespace(
                blocks=0,
                transactions=0,
                candidates=0,
                rollback=2,
            ),
        )

        self.assertEqual(
            before["payments_count"],
            1,
        )

        self.assertEqual(
            after["payments_count"],
            0,
        )

        self.assertEqual(
            after["scan_rollback"],
            2,
        )

        self.assertNotEqual(
            before[
                "snapshot_fingerprint"
            ],
            after[
                "snapshot_fingerprint"
            ],
        )

    def test_mempool_receive_replacement_changes_fingerprint(self):
        wallet = LifecycleWallet()

        db = wallet.scanner.store.db

        db.execute(
            """
            INSERT INTO mempool_coins
            VALUES(?,?,?,?,?,?)
            """,
            (
                "22" * 32,
                0,
                "acct-1",
                7,
                100_000,
                1,
            ),
        )

        first = build_scanner_snapshot(
            wallet,
            METRICS,
        )

        db.execute(
            "DELETE FROM mempool_coins"
        )

        db.execute(
            """
            INSERT INTO mempool_coins
            VALUES(?,?,?,?,?,?)
            """,
            (
                "33" * 32,
                0,
                "acct-1",
                7,
                100_000,
                1,
            ),
        )

        second = build_scanner_snapshot(
            wallet,
            METRICS,
        )

        self.assertEqual(
            first[
                "mempool_coin_count"
            ],
            second[
                "mempool_coin_count"
            ],
        )

        self.assertEqual(
            first[
                "unconfirmed_atoms"
            ],
            second[
                "unconfirmed_atoms"
            ],
        )

        self.assertNotEqual(
            first[
                "snapshot_fingerprint"
            ],
            second[
                "snapshot_fingerprint"
            ],
        )

    def test_mempool_spend_replacement_changes_fingerprint(self):
        wallet = LifecycleWallet()

        db = wallet.scanner.store.db

        db.execute(
            """
            INSERT INTO mempool_spends
            VALUES(?,?,?)
            """,
            (
                "11" * 32,
                0,
                "44" * 32,
            ),
        )

        first = build_scanner_snapshot(
            wallet,
            METRICS,
        )

        db.execute(
            """
            UPDATE mempool_spends
            SET spending=?
            """,
            (
                "55" * 32,
            ),
        )

        second = build_scanner_snapshot(
            wallet,
            METRICS,
        )

        self.assertEqual(
            first[
                "mempool_spend_count"
            ],
            second[
                "mempool_spend_count"
            ],
        )

        self.assertEqual(
            first[
                "pending_spent_atoms"
            ],
            second[
                "pending_spent_atoms"
            ],
        )

        self.assertNotEqual(
            first[
                "snapshot_fingerprint"
            ],
            second[
                "snapshot_fingerprint"
            ],
        )

    def test_mempool_drop_returns_to_original_state(self):
        wallet = LifecycleWallet()

        baseline = build_scanner_snapshot(
            wallet,
            METRICS,
        )

        db = wallet.scanner.store.db

        db.execute(
            """
            INSERT INTO mempool_coins
            VALUES(?,?,?,?,?,?)
            """,
            (
                "66" * 32,
                0,
                "acct-1",
                7,
                123_456,
                None,
            ),
        )

        pending = build_scanner_snapshot(
            wallet,
            METRICS,
        )

        self.assertNotEqual(
            baseline[
                "snapshot_fingerprint"
            ],
            pending[
                "snapshot_fingerprint"
            ],
        )

        db.execute(
            "DELETE FROM mempool_coins"
        )

        dropped = build_scanner_snapshot(
            wallet,
            METRICS,
        )

        self.assertEqual(
            baseline[
                "snapshot_fingerprint"
            ],
            dropped[
                "snapshot_fingerprint"
            ],
        )


if __name__ == "__main__":
    unittest.main()
