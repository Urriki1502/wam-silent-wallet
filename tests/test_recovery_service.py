import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from wam_sp.api import SilentWallet
from wam_sp.backup import create as create_recovery
from wam_sp.keystore import (
    Keyring,
    load_private,
    save_private,
)

from wam_silent_wallet.services.wallet_service import (
    WalletService,
)


PASSWORD = b"correct horse battery staple"


class RecoveryServiceTests(
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

        # Deliberately include all interesting reservation classes.
        db = wallet.scanner.store.db

        db.execute(
            "INSERT INTO reservations VALUES(?,?,?,?,?)",
            (
                "11" * 32,
                0,
                "draft-token",
                "draft",
                1,
            ),
        )

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

        wallet.scanner.store.validate()

        encrypted = ring.backup(
            PASSWORD
        )

        save_private(
            self.service.keys_path,
            encrypted,
        )

        backups = (
            self.root
            / "Backups"
        )

        backups.mkdir()
        os.chmod(
            backups,
            0o700,
        )

        self.bundle = (
            backups
            / "recovery.wspbak"
        )

        envelope = create_recovery(
            ring,
            wallet.scanner,
            PASSWORD,
        )

        save_private(
            self.bundle,
            envelope,
        )

        self.base_address = (
            wallet.get_silent_address()
        )

        wallet.close()
        ring.close()

    def tearDown(self):
        self.root_context.cleanup()

    def _active_hashes(self):
        return (
            hashlib.sha256(
                self.service.db_path.read_bytes()
            ).hexdigest(),
            hashlib.sha256(
                self.service.keys_path.read_bytes()
            ).hexdigest(),
        )

    def test_successful_restore_is_staged_and_spend_blocked(self):
        result = (
            self.service
            .restore_recovery_bundle(
                PASSWORD,
                str(self.bundle),
            )
        )

        self.assertEqual(
            result["base_address"],
            self.base_address,
        )

        self.assertEqual(
            result[
                "draft_reservations_dropped"
            ],
            1,
        )

        self.assertEqual(
            result[
                "protected_reservations"
            ],
            2,
        )

        self.assertTrue(
            result[
                "reconciliation_required"
            ]
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
                    "SELECT state FROM reservations"
                )
            }

            self.assertNotIn(
                "draft",
                states,
            )

            self.assertEqual(
                states,
                {
                    "signed",
                    "manual",
                },
            )

            self.assertEqual(
                wallet.get_silent_address(),
                self.base_address,
            )

        finally:
            wallet.close()
            ring.close()

    def test_wrong_passphrase_does_not_touch_active_wallet(self):
        before = self._active_hashes()

        with self.assertRaisesRegex(
            ValueError,
            "RECOVERY_RESTORE_FAILED",
        ):
            self.service.restore_recovery_bundle(
                b"wrong password is long enough",
                str(self.bundle),
            )

        self.assertEqual(
            self._active_hashes(),
            before,
        )

        self.assertFalse(
            self.service
            .recovery_pending()
        )

    def test_tampered_bundle_does_not_touch_active_wallet(self):
        before = self._active_hashes()

        raw = bytearray(
            load_private(
                self.bundle
            )
        )

        raw[-1] ^= 1

        tampered = (
            self.bundle.parent
            / "tampered.wspbak"
        )

        save_private(
            tampered,
            bytes(raw),
        )

        with self.assertRaisesRegex(
            ValueError,
            "RECOVERY_RESTORE_FAILED",
        ):
            self.service.restore_recovery_bundle(
                PASSWORD,
                str(tampered),
            )

        self.assertEqual(
            self._active_hashes(),
            before,
        )

    def test_activation_failure_rolls_back_old_wallet(self):
        before = self._active_hashes()

        import wam_silent_wallet.services.recovery_service as recovery_module

        original_replace = (
            recovery_module.os.replace
        )

        failed = {
            "value": False
        }

        def guarded_replace(
            source,
            destination,
        ):
            source = Path(
                source
            )

            destination = Path(
                destination
            )

            if (
                not failed["value"]
                and source.name
                == "keys.wsp"
                and source.parent.name.startswith(
                    ".recovery-stage-"
                )
                and destination
                == self.service.keys_path
            ):
                failed["value"] = True
                raise OSError(
                    "simulated activation failure"
                )

            return original_replace(
                source,
                destination,
            )

        with patch(
            "wam_silent_wallet.services.recovery_service.os.replace",
            side_effect=guarded_replace,
        ):
            with self.assertRaisesRegex(
                ValueError,
                "RECOVERY_ACTIVATION_FAILED",
            ):
                self.service.restore_recovery_bundle(
                    PASSWORD,
                    str(self.bundle),
                )

        self.assertTrue(
            failed["value"]
        )

        self.assertEqual(
            self._active_hashes(),
            before,
        )

        self.assertFalse(
            self.service
            .recovery_pending()
        )


if __name__ == "__main__":
    unittest.main()
