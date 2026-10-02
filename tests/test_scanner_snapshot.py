import sqlite3
from types import SimpleNamespace
import unittest

from wam_silent_wallet.services.scanner_snapshot import (
    build_scanner_snapshot,
)


TIP = "aa" * 32


class FakeStore:
    def __init__(self):
        self.db = sqlite3.connect(
            ":memory:"
        )

        self.db.row_factory = (
            sqlite3.Row
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
                public_key TEXT,
                tweak TEXT,
                label INTEGER,
                k INTEGER
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

        self.db.executemany(
            """
            INSERT INTO coins
            VALUES(?,?,?,?,?,?,?)
            """,
            [
                (
                    "11" * 32,
                    0,
                    100_000,
                    None,
                    7,
                    9,
                    None,
                ),
                (
                    "22" * 32,
                    1,
                    200_000,
                    1,
                    7,
                    10,
                    None,
                ),
            ],
        )

        self.db.execute(
            """
            INSERT INTO history
            VALUES(?)
            """,
            (
                "33" * 32,
            ),
        )

    def tip(self):
        return (
            10,
            TIP,
        )


class FakeScanner:
    def __init__(self):
        self.store = FakeStore()

        self.accounts = (
            SimpleNamespace(
                account_id="acct-1",
                epoch=7,
            ),
        )

        self.ready = True
        self.mempool_ready = True

        self.verified_tip = (
            10,
            TIP,
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


class FakeWallet:
    def __init__(self):
        self.scanner = FakeScanner()

    def get_balance(self):
        return {
            "confirmed_atoms": 300_000,
            "reserved_atoms": 0,
            "available_atoms": 300_000,
            "unconfirmed_atoms": 0,
            "pending_spent_atoms": 0,
        }


METRICS = SimpleNamespace(
    blocks=1,
    transactions=2,
    candidates=1,
    rollback=0,
)


class ScannerSnapshotTests(
    unittest.TestCase
):
    def test_verified_snapshot_normalizes_labels(self):
        wallet = FakeWallet()

        result = build_scanner_snapshot(
            wallet,
            METRICS,
        )

        self.assertTrue(
            result["scanner_current"]
        )

        self.assertTrue(
            result["mempool_current"]
        )

        self.assertEqual(
            result["payments_count"],
            2,
        )

        # Newest first.
        self.assertEqual(
            result["payments"][0][
                "label_name"
            ],
            "Invoice 001",
        )

        self.assertEqual(
            result["payments"][1][
                "label_name"
            ],
            "Base",
        )

        self.assertEqual(
            len(
                result[
                    "snapshot_fingerprint"
                ]
            ),
            64,
        )

    def test_duplicate_outpoint_is_rejected(self):
        wallet = FakeWallet()

        wallet.scanner.store.db.execute(
            """
            INSERT INTO coins
            VALUES(?,?,?,?,?,?,?)
            """,
            (
                "22" * 32,
                1,
                200_000,
                1,
                7,
                10,
                None,
            ),
        )

        with self.assertRaisesRegex(
            ValueError,
            "SCANNER_DUPLICATE_OUTPOINT",
        ):
            build_scanner_snapshot(
                wallet,
                METRICS,
            )

    def test_stale_scanner_is_rejected(self):
        wallet = FakeWallet()

        wallet.scanner.ready = False

        with self.assertRaisesRegex(
            ValueError,
            "SCAN_NOT_CURRENT",
        ):
            build_scanner_snapshot(
                wallet,
                METRICS,
            )

    def test_incomplete_mempool_is_rejected(self):
        wallet = FakeWallet()

        wallet.scanner.mempool_ready = (
            False
        )

        with self.assertRaisesRegex(
            ValueError,
            "MEMPOOL_NOT_CURRENT",
        ):
            build_scanner_snapshot(
                wallet,
                METRICS,
            )

    def test_missing_label_metadata_is_rejected(self):
        wallet = FakeWallet()

        wallet.scanner.store.db.execute(
            "DELETE FROM labels"
        )

        with self.assertRaisesRegex(
            ValueError,
            "SCANNER_LABEL_METADATA_MISSING",
        ):
            build_scanner_snapshot(
                wallet,
                METRICS,
            )

    def test_snapshot_is_idempotent(self):
        wallet = FakeWallet()

        first = build_scanner_snapshot(
            wallet,
            METRICS,
        )

        second = build_scanner_snapshot(
            wallet,
            METRICS,
        )

        self.assertEqual(
            first[
                "snapshot_fingerprint"
            ],
            second[
                "snapshot_fingerprint"
            ],
        )

        self.assertEqual(
            first["payments"],
            second["payments"],
        )

    def test_label_metadata_change_changes_fingerprint(self):
        wallet = FakeWallet()

        first = build_scanner_snapshot(
            wallet,
            METRICS,
        )

        wallet.scanner.store.db.execute(
            """
            UPDATE labels
            SET name=?
            WHERE account=?
              AND label=?
            """,
            (
                "Invoice 001 revised",
                "acct-1",
                1,
            ),
        )

        second = build_scanner_snapshot(
            wallet,
            METRICS,
        )

        self.assertNotEqual(
            first[
                "snapshot_fingerprint"
            ],
            second[
                "snapshot_fingerprint"
            ],
        )

        self.assertEqual(
            second["payments"][0][
                "label_name"
            ],
            "Invoice 001 revised",
        )

    def test_reserved_label_zero_is_filtered_before_pagination(self):
        wallet = FakeWallet()

        # Insert protocol-reserved label-0 rows newer than all
        # user-visible payments. They must never consume UI slots.
        for index in range(20):
            wallet.scanner.store.db.execute(
                """
                INSERT INTO coins
                VALUES(?,?,?,?,?,?,?)
                """,
                (
                    f"{index + 100:064x}",
                    0,
                    1,
                    0,
                    7,
                    10,
                    None,
                ),
            )

        result = build_scanner_snapshot(
            wallet,
            METRICS,
        )

        self.assertEqual(
            result[
                "reserved_label_zero_count"
            ],
            20,
        )

        self.assertEqual(
            result["payments_count"],
            2,
        )

        self.assertEqual(
            len(result["payments"]),
            2,
        )

        self.assertTrue(
            all(
                item["label"] != 0
                for item
                in result["payments"]
            )
        )


if __name__ == "__main__":
    unittest.main()
