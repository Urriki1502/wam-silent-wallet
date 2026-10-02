from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from wam_sp.psbt import (
    PSBT,
    Tx,
)

from wam_silent_wallet.services.payment_journal import (
    PaymentJournalService,
)
from wam_silent_wallet.services.payment_reconciliation import (
    PaymentReconciliationService,
)
from wam_silent_wallet.services.wallet_service import (
    WalletService,
)


TOKEN = "reconcile-token"
MANIFEST = "44" * 32
INPUT_TXID = "11" * 32

XONLY = bytes.fromhex(
    "79be667ef9dcbbac55a06295ce870b07"
    "029bfcdb2dce28d959f2815b16f81798"
)

SCRIPT = (
    b"\x51\x20"
    + XONLY
)


def make_psbt():
    return PSBT(
        tx=Tx(
            inputs=(
                (
                    INPUT_TXID,
                    1,
                ),
            ),
            outputs=(
                (
                    900,
                    SCRIPT,
                ),
            ),
        ),
        utxos=(
            (
                1000,
                SCRIPT,
            ),
        ),
        signatures=(
            b"\x01" * 64,
        ),
    ).encode()


SIGNED_PSBT = make_psbt()

TXID = (
    PSBT.decode(
        SIGNED_PSBT
    )
    .txid()
)


class FakeStore:
    def __init__(
        self,
    ):
        self.db = sqlite3.connect(
            ":memory:"
        )

        self.db.row_factory = (
            sqlite3.Row
        )

        self.db.executescript(
            """
            CREATE TABLE reservations(
                txid TEXT,
                vout INTEGER,
                token TEXT,
                state TEXT,
                created INTEGER
            );

            CREATE TABLE history(
                txid TEXT,
                height INTEGER,
                credit INTEGER,
                debit INTEGER
            );

            CREATE TABLE mempool_spends(
                txid TEXT,
                vout INTEGER,
                spending TEXT
            );
            """
        )

    @contextmanager
    def transaction(
        self,
    ):
        try:
            yield self.db
            self.db.commit()

        except Exception:
            self.db.rollback()
            raise


class FakeWallet:
    def __init__(
        self,
        state,
    ):
        store = FakeStore()

        self.scanner = type(
            "Scanner",
            (),
            {
                "store": store,
            },
        )()

        store.db.execute(
            """
            INSERT INTO reservations
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                INPUT_TXID,
                1,
                TOKEN,
                state,
                1,
            ),
        )

        store.db.commit()


class FakeChain:
    def __init__(
        self,
        mempool=None,
    ):
        self.mempool = (
            list(
                mempool or []
            )
        )

    def call(
        self,
        method,
        params=None,
    ):
        if method != "getrawmempool":
            raise AssertionError(
                method
            )

        return list(
            self.mempool
        )


class PaymentReconciliationTests(
    unittest.TestCase
):
    def make_journal(
        self,
    ):
        tmp = tempfile.TemporaryDirectory()

        root = Path(
            tmp.name
        )

        os.chmod(
            root,
            0o700,
        )

        journal = (
            PaymentJournalService(
                root
            )
        )

        journal.record_signed(
            TOKEN,
            MANIFEST,
            SIGNED_PSBT,
        )

        return (
            tmp,
            journal,
        )

    def test_signed_material_promotes_draft(self):
        tmp, journal = (
            self.make_journal()
        )

        try:
            wallet = FakeWallet(
                "draft"
            )

            service = (
                PaymentReconciliationService(
                    journal
                )
            )

            result = service.reconcile(
                wallet,
                FakeChain(),
            )

            row = (
                wallet
                .scanner
                .store
                .db
                .execute(
                    """
                    SELECT state
                    FROM reservations
                    WHERE token=?
                    """,
                    (TOKEN,),
                )
                .fetchone()
            )

            self.assertEqual(
                row["state"],
                "signed",
            )

            self.assertEqual(
                journal.load(
                    TOKEN
                )["state"],
                "signed",
            )

            self.assertEqual(
                result["unresolved"],
                1,
            )

        finally:
            tmp.cleanup()

    def test_mempool_transaction_finalizes_broadcast(self):
        tmp, journal = (
            self.make_journal()
        )

        try:
            journal.transition(
                TOKEN,
                "signed",
            )

            journal.transition(
                TOKEN,
                "broadcasting",
            )

            wallet = FakeWallet(
                "signed"
            )

            result = (
                PaymentReconciliationService(
                    journal
                )
                .reconcile(
                    wallet,
                    FakeChain(
                        [TXID]
                    ),
                )
            )

            self.assertEqual(
                journal.load(
                    TOKEN
                )["state"],
                "broadcast",
            )

            self.assertEqual(
                result["broadcast"],
                1,
            )

        finally:
            tmp.cleanup()

    def test_absent_broadcasting_becomes_uncertain(self):
        tmp, journal = (
            self.make_journal()
        )

        try:
            journal.transition(
                TOKEN,
                "signed",
            )

            journal.transition(
                TOKEN,
                "broadcasting",
            )

            wallet = FakeWallet(
                "signed"
            )

            result = (
                PaymentReconciliationService(
                    journal
                )
                .reconcile(
                    wallet,
                    FakeChain(),
                )
            )

            self.assertEqual(
                journal.load(
                    TOKEN
                )["state"],
                "uncertain",
            )

            row = (
                wallet
                .scanner
                .store
                .db
                .execute(
                    """
                    SELECT state
                    FROM reservations
                    WHERE token=?
                    """,
                    (TOKEN,),
                )
                .fetchone()
            )

            self.assertEqual(
                row["state"],
                "uncertain",
            )

            self.assertEqual(
                result["uncertain"],
                1,
            )

        finally:
            tmp.cleanup()

    def test_confirmed_history_finalizes_broadcast(self):
        tmp, journal = (
            self.make_journal()
        )

        try:
            journal.transition(
                TOKEN,
                "signed",
            )

            journal.transition(
                TOKEN,
                "broadcasting",
            )

            journal.transition(
                TOKEN,
                "uncertain",
            )

            wallet = FakeWallet(
                "uncertain"
            )

            db = (
                wallet
                .scanner
                .store
                .db
            )

            db.execute(
                """
                INSERT INTO history
                VALUES (?, ?, ?, ?)
                """,
                (
                    TXID,
                    100,
                    0,
                    1000,
                ),
            )

            db.commit()

            result = (
                PaymentReconciliationService(
                    journal
                )
                .reconcile(
                    wallet,
                    FakeChain(),
                )
            )

            self.assertEqual(
                journal.load(
                    TOKEN
                )["state"],
                "broadcast",
            )

            self.assertEqual(
                result["broadcast"],
                1,
            )

        finally:
            tmp.cleanup()

    def test_reconciliation_is_idempotent_after_resolution(self):
        tmp, journal = (
            self.make_journal()
        )

        try:
            journal.transition(
                TOKEN,
                "signed",
            )

            journal.transition(
                TOKEN,
                "broadcasting",
            )

            wallet = FakeWallet(
                "signed"
            )

            service = (
                PaymentReconciliationService(
                    journal
                )
            )

            service.reconcile(
                wallet,
                FakeChain(
                    [TXID]
                ),
            )

            second = (
                service.reconcile(
                    wallet,
                    FakeChain(),
                )
            )

            self.assertEqual(
                second["checked"],
                0,
            )

        finally:
            tmp.cleanup()

    def test_spend_gate_blocks_unresolved_payment(self):
        service = object.__new__(
            WalletService
        )

        service.recovery = type(
            "Recovery",
            (),
            {
                "pending": lambda self: False,
            },
        )()

        service.payment_journal = type(
            "Journal",
            (),
            {
                "has_unresolved": (
                    lambda self: True
                ),
            },
        )()

        with self.assertRaisesRegex(
            ValueError,
            "PAYMENT_RECONCILIATION_REQUIRED",
        ):
            service.assert_spend_ready()


if __name__ == "__main__":
    unittest.main()
