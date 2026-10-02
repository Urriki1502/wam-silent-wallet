from pathlib import Path
import tempfile
import unittest

from wam_silent_wallet.services.wallet_service import (
    WalletService,
)


class StartupIntegrityTests(
    unittest.TestCase
):
    def test_fresh_runtime_without_wallet_is_allowed(self):
        with tempfile.TemporaryDirectory() as root:
            service = WalletService(
                Path(root)
            )

            self.assertFalse(
                service.exists()
            )

    def test_db_without_keys_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)

            (
                root
                / "wallet.db"
            ).write_bytes(
                b"partial"
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "WALLET_FILESET_INCOMPLETE",
            ):
                WalletService(
                    root
                )

    def test_keys_without_db_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)

            (
                root
                / "keys.wsp"
            ).write_bytes(
                b"partial"
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "WALLET_FILESET_INCOMPLETE",
            ):
                WalletService(
                    root
                )

    def test_wallet_db_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)

            target = (
                root
                / "outside.db"
            )

            target.write_bytes(
                b"x"
            )

            (
                root
                / "wallet.db"
            ).symlink_to(
                target
            )

            (
                root
                / "keys.wsp"
            ).write_bytes(
                b"keys"
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "WALLET_FILESET_SYMLINK",
            ):
                WalletService(
                    root
                )


if __name__ == "__main__":
    unittest.main()
