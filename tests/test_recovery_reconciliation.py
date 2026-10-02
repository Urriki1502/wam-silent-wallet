import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from wam_sp.api import SilentWallet
from wam_sp.backup import create as create_recovery
from wam_sp.core import compressed
from wam_sp.keystore import (
    Keyring,
    save_private,
)
from wam_sp.watcher import GENESIS

from wam_silent_wallet.services.wallet_service import (
    WalletService,
)


PASSWORD = b"correct horse battery staple"


class RecoveryReconciliationTests(
    unittest.TestCase
):
    def setUp(self):
        self.root_context = (
            tempfile.TemporaryDirectory()
        )

        self.root = Path(
            self.root_context.name
        )

        os.chmod(
            self.root,
            0o700,
        )

        self.service = WalletService(
            self.root
        )

        ring = Keyring()

        wallet = SilentWallet(
            self.service.db_path,
            ring.accounts(),
        )

        db = wallet.scanner.store.db

        db.execute(
            "INSERT INTO reservations VALUES(?,?,?,?,?)",
            (
                "22" * 32,
                0,
                "signed-token",
                "signed",
                1,
            ),
        )

        db.execute(
            "INSERT INTO reservations VALUES(?,?,?,?,?)",
            (
                "33" * 32,
                0,
                "manual-token",
                "manual",
                1,
            ),
        )

        save_private(
            self.service.keys_path,
            ring.backup(
                PASSWORD
            ),
        )

        backup_dir = (
            self.root
            / "Backups"
        )

        backup_dir.mkdir()
        os.chmod(
            backup_dir,
            0o700,
        )

        self.bundle = (
            backup_dir
            / "recovery.wspbak"
        )

        save_private(
            self.bundle,
            create_recovery(
                ring,
                wallet.scanner,
                PASSWORD,
            ),
        )

        wallet.close()
        ring.close()

        self.service.restore_recovery_bundle(
            PASSWORD,
            str(self.bundle),
        )

        self.assertTrue(
            self.service
            .recovery_pending()
        )

    def tearDown(self):
        self.root_context.cleanup()

    @staticmethod
    def _materialize_chain(
        wallet,
        *,
        signed_spent=False,
        signed_mempool=False,
    ):
        scanner = wallet.scanner
        store = scanner.store
        db = store.db

        account = (
            scanner.accounts[0]
        )

        block_hash = "aa" * 32

        def public_key(
            tweak,
        ):
            return (
                compressed(
                    account.spend_public
                )
                .add(
                    tweak.to_bytes(
                        32,
                        "big",
                    )
                )
                .format()[1:]
                .hex()
            )

        with store.transaction():
            db.execute(
                """
                INSERT INTO blocks
                VALUES(?,?,?)
                """,
                (
                    1,
                    block_hash,
                    GENESIS,
                ),
            )

            db.execute(
                """
                INSERT INTO coins
                VALUES(
                    ?,?,?,?,?,?,?,?,?,?,?
                )
                """,
                (
                    "22" * 32,
                    0,
                    account.account_id,
                    account.epoch,
                    1_000_000,
                    public_key(1),
                    format(
                        1,
                        "064x",
                    ),
                    None,
                    0,
                    1,
                    (
                        1
                        if signed_spent
                        else None
                    ),
                ),
            )

            db.execute(
                """
                INSERT INTO coins
                VALUES(
                    ?,?,?,?,?,?,?,?,?,?,?
                )
                """,
                (
                    "33" * 32,
                    0,
                    account.account_id,
                    account.epoch,
                    2_000_000,
                    public_key(2),
                    format(
                        2,
                        "064x",
                    ),
                    None,
                    0,
                    1,
                    None,
                ),
            )

            if signed_mempool:
                db.execute(
                    """
                    INSERT INTO mempool_spends
                    VALUES(?,?,?)
                    """,
                    (
                        "22" * 32,
                        0,
                        "44" * 32,
                    ),
                )

            store.validate()

        scanner.ready = True
        scanner.verified_tip = (
            store.tip()
        )
        scanner.mempool_ready = True

        return SimpleNamespace(
            blocks=1,
            transactions=1,
            rollback=0,
        )

    def _fake_scan(
        self,
        *,
        signed_spent=False,
        signed_mempool=False,
    ):
        test = self

        def scan(
            wallet,
            chain,
            mempool=False,
        ):
            self.assertTrue(
                mempool
            )

            return test._materialize_chain(
                wallet,
                signed_spent=(
                    signed_spent
                ),
                signed_mempool=(
                    signed_mempool
                ),
            )

        return scan

    def test_successful_reconcile_unlocks_spending(self):
        with patch.object(
            SilentWallet,
            "scan",
            new=self._fake_scan(),
        ):
            result = (
                self.service
                .reconcile_recovery(
                    PASSWORD,
                    object(),
                )
            )

        self.assertFalse(
            self.service
            .recovery_pending()
        )

        self.service.assert_spend_ready()

        self.assertEqual(
            result["manual_locked"],
            1,
        )

        self.assertEqual(
            result["uncertain_locked"],
            1,
        )

        ring, wallet = (
            self.service._open(
                PASSWORD
            )
        )

        try:
            states = {
                row["state"]
                for row
                in wallet.scanner.store.db.execute(
                    """
                    SELECT state
                    FROM reservations
                    """
                )
            }

            self.assertEqual(
                states,
                {
                    "manual",
                    "uncertain",
                },
            )

        finally:
            wallet.close()
            ring.close()

    def test_confirmed_spend_resolves_signed_lock(self):
        with patch.object(
            SilentWallet,
            "scan",
            new=self._fake_scan(
                signed_spent=True,
            ),
        ):
            result = (
                self.service
                .reconcile_recovery(
                    PASSWORD,
                    object(),
                )
            )

        self.assertEqual(
            result[
                "resolved_confirmed"
            ],
            1,
        )

        ring, wallet = (
            self.service._open(
                PASSWORD
            )
        )

        try:
            rows = list(
                wallet.scanner.store.db.execute(
                    """
                    SELECT state
                    FROM reservations
                    """
                )
            )

            self.assertEqual(
                [
                    row["state"]
                    for row in rows
                ],
                [
                    "manual",
                ],
            )

        finally:
            wallet.close()
            ring.close()

    def test_mempool_spend_remains_locked_uncertain(self):
        with patch.object(
            SilentWallet,
            "scan",
            new=self._fake_scan(
                signed_mempool=True,
            ),
        ):
            result = (
                self.service
                .reconcile_recovery(
                    PASSWORD,
                    object(),
                )
            )

        self.assertEqual(
            result["mempool_locked"],
            1,
        )

        self.assertEqual(
            result["uncertain_locked"],
            1,
        )

    def test_scan_failure_keeps_spend_gate(self):
        def fail_scan(
            wallet,
            chain,
            mempool=False,
        ):
            raise ValueError(
                "NODE_DOWN"
            )

        with patch.object(
            SilentWallet,
            "scan",
            new=fail_scan,
        ):
            with self.assertRaisesRegex(
                ValueError,
                "RECOVERY_RECONCILIATION_FAILED",
            ):
                self.service.reconcile_recovery(
                    PASSWORD,
                    object(),
                )

        self.assertTrue(
            self.service
            .recovery_pending()
        )

        with self.assertRaisesRegex(
            ValueError,
            "RECOVERY_RESCAN_REQUIRED",
        ):
            self.service.assert_spend_ready()

    def test_database_marker_survives_sidecar_loss(self):
        self.service.recovery.pending_path.unlink()

        self.assertTrue(
            self.service
            .recovery_pending()
        )

        with self.assertRaisesRegex(
            ValueError,
            "RECOVERY_RESCAN_REQUIRED",
        ):
            self.service.assert_spend_ready()


if __name__ == "__main__":
    unittest.main()
