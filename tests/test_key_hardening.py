import os
from pathlib import Path
import tempfile
import unittest

from wam_sp.api import SilentWallet
from wam_sp.keystore import (
    Keyring,
    save_private,
)

from wam_silent_wallet.services.key_protection import (
    KEY_KDF_MAGIC,
)
from wam_silent_wallet.services.wallet_service import (
    WalletService,
)


PASSWORD = b"correct horse battery staple"


class KeyHardeningTests(unittest.TestCase):
    def _root(self):
        context = tempfile.TemporaryDirectory()
        self.addCleanup(context.cleanup)

        root = Path(
            context.name
        )

        os.chmod(
            root,
            0o700,
        )

        return root

    def _legacy_wallet(self):
        root = self._root()
        service = WalletService(
            root
        )

        ring = Keyring()
        wallet = SilentWallet(
            service.db_path,
            ring.accounts(),
        )

        save_private(
            service.keys_path,
            ring.backup(
                PASSWORD
            ),
        )

        return (
            service,
            ring,
            wallet,
        )

    def test_legacy_keys_migrate_and_reopen(self):
        service, ring, wallet = (
            self._legacy_wallet()
        )

        address = (
            wallet.get_silent_address()
        )

        wallet.close()
        ring.close()

        migrated_ring, migrated_wallet = (
            service._open(
                PASSWORD
            )
        )

        try:
            self.assertEqual(
                service.keys_path
                .read_bytes()[:8],
                KEY_KDF_MAGIC,
            )

            self.assertEqual(
                migrated_wallet
                .get_silent_address(),
                address,
            )
        finally:
            migrated_wallet.close()
            migrated_ring.close()

        reopened_ring, reopened_wallet = (
            service._open(
                PASSWORD
            )
        )

        reopened_wallet.close()
        reopened_ring.close()

    def test_db_ahead_label_is_reconciled_after_crash_window(self):
        service, ring, wallet = (
            self._legacy_wallet()
        )

        created = wallet.create_labeled_address(
            name="Recovered label",
            epoch=0,
            label=7,
        )

        self.assertEqual(
            created["label"],
            7,
        )

        wallet.close()
        ring.close()

        recovered_ring, recovered_wallet = (
            service._open(
                PASSWORD
            )
        )

        try:
            account = (
                recovered_ring
                .accounts()[0]
            )

            self.assertIn(
                7,
                account.labels,
            )

            self.assertEqual(
                service.keys_path
                .read_bytes()[:8],
                KEY_KDF_MAGIC,
            )

            self.assertEqual(
                recovered_wallet
                .get_silent_address(
                    epoch=0,
                    label=7,
                ),
                created["address"],
            )
        finally:
            recovered_wallet.close()
            recovered_ring.close()


if __name__ == "__main__":
    unittest.main()
