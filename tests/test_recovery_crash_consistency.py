import json
from pathlib import Path
import tempfile
import unittest

from wam_silent_wallet.services.recovery_service import (
    RecoveryService,
)
from wam_silent_wallet.services.wallet_service import (
    WalletService,
)


class RecoveryCrashConsistencyTests(
    unittest.TestCase
):
    def setUp(self):
        self.context = (
            tempfile.TemporaryDirectory()
        )

        self.root = Path(
            self.context.name
        )

        self.db = (
            self.root
            / "wallet.db"
        )

        self.keys = (
            self.root
            / "keys.wsp"
        )

        self.pending = (
            self.root
            / "recovery-pending.json"
        )

        self.service = RecoveryService(
            self.root,
            self.db,
            self.keys,
        )

    def tearDown(self):
        self.context.cleanup()

    def _journal(
        self,
        *,
        phase,
        rollback,
        presence,
    ):
        payload = {
            "version": 1,
            "phase": phase,
            "rollback_dir": (
                rollback.name
            ),
            "original_presence": (
                presence
            ),
        }

        self.service.activation_journal_path.write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    def test_partial_activation_rolls_back_old_wallet(self):
        self.db.write_bytes(
            b"new-db"
        )

        rollback = (
            self.root
            / ".recovery-rollback-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        )

        rollback.mkdir()

        (
            rollback
            / "wallet.db"
        ).write_bytes(
            b"old-db"
        )

        (
            rollback
            / "keys.wsp"
        ).write_bytes(
            b"old-keys"
        )

        self._journal(
            phase="new-installed",
            rollback=rollback,
            presence={
                "wallet.db": True,
                "keys.wsp": True,
                "recovery-pending.json": False,
            },
        )

        result = (
            self.service
            .recover_interrupted_activation()
        )

        self.assertEqual(
            result,
            "rolled-back",
        )

        self.assertEqual(
            self.db.read_bytes(),
            b"old-db",
        )

        self.assertEqual(
            self.keys.read_bytes(),
            b"old-keys",
        )

        self.assertFalse(
            self.pending.exists()
        )

        self.assertFalse(
            rollback.exists()
        )

        self.assertFalse(
            self.service
            .activation_journal_path
            .exists()
        )

    def test_partial_old_move_is_repaired(self):
        self.keys.write_bytes(
            b"old-keys"
        )

        rollback = (
            self.root
            / ".recovery-rollback-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        )

        rollback.mkdir()

        (
            rollback
            / "wallet.db"
        ).write_bytes(
            b"old-db"
        )

        self._journal(
            phase="prepared",
            rollback=rollback,
            presence={
                "wallet.db": True,
                "keys.wsp": True,
                "recovery-pending.json": False,
            },
        )

        result = (
            self.service
            .recover_interrupted_activation()
        )

        self.assertEqual(
            result,
            "rolled-back",
        )

        self.assertEqual(
            self.db.read_bytes(),
            b"old-db",
        )

        self.assertEqual(
            self.keys.read_bytes(),
            b"old-keys",
        )

    def test_verified_activation_is_finalized_not_rolled_back(self):
        self.db.write_bytes(
            b"recovered-db"
        )

        self.keys.write_bytes(
            b"recovered-keys"
        )

        self.pending.write_text(
            "{}",
            encoding="utf-8",
        )

        rollback = (
            self.root
            / ".recovery-rollback-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        )

        rollback.mkdir()

        (
            rollback
            / "wallet.db"
        ).write_bytes(
            b"old-db"
        )

        (
            rollback
            / "keys.wsp"
        ).write_bytes(
            b"old-keys"
        )

        self._journal(
            phase="verified",
            rollback=rollback,
            presence={
                "wallet.db": True,
                "keys.wsp": True,
                "recovery-pending.json": False,
            },
        )

        result = (
            self.service
            .recover_interrupted_activation()
        )

        self.assertEqual(
            result,
            "finalized",
        )

        self.assertEqual(
            self.db.read_bytes(),
            b"recovered-db",
        )

        self.assertEqual(
            self.keys.read_bytes(),
            b"recovered-keys",
        )

        self.assertFalse(
            rollback.exists()
        )

    def test_wallet_service_repairs_interrupted_activation_on_start(self):
        rollback = (
            self.root
            / ".recovery-rollback-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        )

        rollback.mkdir()

        (
            rollback
            / "wallet.db"
        ).write_bytes(
            b"old-db"
        )

        (
            rollback
            / "keys.wsp"
        ).write_bytes(
            b"old-keys"
        )

        self.db.write_bytes(
            b"partial-new-db"
        )

        self._journal(
            phase="new-installed",
            rollback=rollback,
            presence={
                "wallet.db": True,
                "keys.wsp": True,
                "recovery-pending.json": False,
            },
        )

        WalletService(
            self.root
        )

        self.assertEqual(
            self.db.read_bytes(),
            b"old-db",
        )

        self.assertEqual(
            self.keys.read_bytes(),
            b"old-keys",
        )

        self.assertFalse(
            self.service
            .activation_journal_path
            .exists()
        )


if __name__ == "__main__":
    unittest.main()
