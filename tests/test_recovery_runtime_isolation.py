import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from wam_silent_wallet.services.wallet_service import (
    WalletService,
)


class RecoveryRuntimeIsolationTests(
    unittest.TestCase
):
    def test_environment_can_isolate_runtime_wallet(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.dict(
                os.environ,
                {
                    "WAM_SILENT_WALLET_DATA_DIR": root,
                },
            ):
                service = WalletService()

            self.assertEqual(
                service.data_dir,
                Path(root),
            )

            self.assertEqual(
                service.db_path,
                Path(root) / "wallet.db",
            )

            self.assertEqual(
                service.keys_path,
                Path(root) / "keys.wsp",
            )


if __name__ == "__main__":
    unittest.main()
