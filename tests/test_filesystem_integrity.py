import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

from wam_silent_wallet.services.config_service import (
    ConfigService,
)
from wam_silent_wallet.services.filesystem_integrity import (
    harden_private_directory,
    harden_private_file,
)
from wam_silent_wallet.services.recovery_service import (
    RecoveryService,
)
from wam_silent_wallet.services.wallet_service import (
    WalletService,
)


@unittest.skipUnless(
    os.name == "posix",
    "POSIX filesystem security test",
)
class FilesystemIntegrityTests(
    unittest.TestCase
):
    def test_private_directory_mode_is_repaired(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = (
                Path(tmp)
                / "private"
            )

            path.mkdir()
            os.chmod(
                path,
                0o755,
            )

            harden_private_directory(
                path,
                create=False,
                code="UNSAFE",
            )

            self.assertEqual(
                stat.S_IMODE(
                    path.stat().st_mode
                ),
                0o700,
            )

    def test_private_file_mode_is_repaired(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = (
                Path(tmp)
                / "secret"
            )

            path.write_bytes(
                b"secret"
            )

            os.chmod(
                path,
                0o644,
            )

            harden_private_file(
                path,
                required=True,
                code="UNSAFE",
            )

            self.assertEqual(
                stat.S_IMODE(
                    path.stat().st_mode
                ),
                0o600,
            )

    def test_private_file_hardlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            path = (
                root
                / "secret"
            )

            linked = (
                root
                / "linked"
            )

            path.write_bytes(
                b"secret"
            )

            os.link(
                path,
                linked,
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "UNSAFE",
            ):
                harden_private_file(
                    path,
                    required=True,
                    code="UNSAFE",
                )

    def test_wallet_runtime_directory_and_database_modes_are_repaired(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            os.chmod(
                root,
                0o755,
            )

            db = root / "wallet.db"
            keys = root / "keys.wsp"

            db.write_bytes(
                b"placeholder-db"
            )

            keys.write_bytes(
                b"placeholder-keys"
            )

            os.chmod(
                db,
                0o644,
            )

            # Private keys are different from ordinary runtime files:
            # an exposed key file must be rejected by key preflight,
            # not silently "repaired" after exposure.
            os.chmod(
                keys,
                0o600,
            )

            WalletService(
                root
            )

            self.assertEqual(
                stat.S_IMODE(
                    root.stat().st_mode
                ),
                0o700,
            )

            self.assertEqual(
                stat.S_IMODE(
                    db.stat().st_mode
                ),
                0o600,
            )

            self.assertEqual(
                stat.S_IMODE(
                    keys.stat().st_mode
                ),
                0o600,
            )

    def test_config_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            target = (
                root
                / "target.json"
            )

            target.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "network": "regtest",
                        "rpc_url": "http://127.0.0.1:18443",
                        "cookie_path": str(
                            root / ".cookie"
                        ),
                        "sync_interval_seconds": 15.0,
                        "fee_tier": "Normal",
                    }
                )
            )

            path = (
                root
                / "config.json"
            )

            path.symlink_to(
                target
            )

            with self.assertRaisesRegex(
                ValueError,
                "CONFIG_FILE_UNSAFE",
            ):
                ConfigService(
                    path
                ).load()

    def test_config_mode_is_repaired_on_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            path = (
                root
                / "config.json"
            )

            service = ConfigService(
                path
            )

            service.save(
                service.defaults()
            )

            os.chmod(
                path,
                0o644,
            )

            service.load()

            self.assertEqual(
                stat.S_IMODE(
                    path.stat().st_mode
                ),
                0o600,
            )

    def test_activation_journal_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            target = (
                root
                / "outside.json"
            )

            target.write_text(
                "{}"
            )

            journal = (
                root
                / ".recovery-activation.json"
            )

            journal.symlink_to(
                target
            )

            service = RecoveryService(
                root,
                root / "wallet.db",
                root / "keys.wsp",
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "RECOVERY_ACTIVATION_JOURNAL_UNSAFE",
            ):
                service.recover_interrupted_activation()

    def test_activation_journal_rejects_rollback_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            journal = (
                root
                / ".recovery-activation.json"
            )

            journal.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "phase": "prepared",
                        "rollback_dir": "../../escape",
                        "original_presence": {},
                    }
                )
            )

            os.chmod(
                journal,
                0o600,
            )

            service = RecoveryService(
                root,
                root / "wallet.db",
                root / "keys.wsp",
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "RECOVERY_ACTIVATION_JOURNAL_INVALID",
            ):
                service.recover_interrupted_activation()

    def test_recovery_pending_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            target = (
                root
                / "outside-pending.json"
            )

            target.write_text(
                "{}"
            )

            pending = (
                root
                / "recovery-pending.json"
            )

            pending.symlink_to(
                target
            )

            service = RecoveryService(
                root,
                root / "wallet.db",
                root / "keys.wsp",
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "RECOVERY_PENDING_FILE_UNSAFE",
            ):
                service.pending()


if __name__ == "__main__":
    unittest.main()
