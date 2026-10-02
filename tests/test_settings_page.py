import os
os.environ.setdefault(
    "QT_QPA_PLATFORM",
    "offscreen",
)

from pathlib import Path
import tempfile
import unittest

from PySide6.QtWidgets import QApplication

from wam_silent_wallet.pages.settings_page import SettingsPage
from wam_silent_wallet.services.config_service import ConfigService


class SettingsPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = (
            QApplication.instance()
            or QApplication([])
        )

    def test_save_persists_valid_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            service = ConfigService(path)
            config = service.load_or_create()

            page = SettingsPage(
                service,
                config,
            )

            page.sync_interval.setValue(
                30.0
            )

            page.fee_tier.setCurrentText(
                "Priority"
            )

            saved = []

            page.settings_saved.connect(
                saved.append
            )

            page.save_settings()

            self.assertEqual(
                len(saved),
                1,
            )

            self.assertEqual(
                saved[0].sync_interval_seconds,
                30.0,
            )

            self.assertEqual(
                saved[0].fee_tier,
                "Priority",
            )

            self.assertEqual(
                service.load(),
                saved[0],
            )

    def test_invalid_rpc_is_rejected_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            service = ConfigService(path)
            config = service.load_or_create()

            page = SettingsPage(
                service,
                config,
            )

            page.rpc_url.setText(
                "http://localhost:18443"
            )

            emitted = []

            page.settings_saved.connect(
                emitted.append
            )

            page.save_settings()

            self.assertEqual(
                emitted,
                [],
            )

            self.assertEqual(
                service.load(),
                config,
            )

            self.assertIn(
                "CONFIG_RPC_URL",
                page.status.text(),
            )

    def test_load_defaults_does_not_save_until_confirmed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            service = ConfigService(path)

            custom = service.save(
                {
                    "version": 1,
                    "network": "regtest",
                    "rpc_url": "http://127.0.0.1:19443",
                    "cookie_path": str(
                        Path(tmp) / ".cookie"
                    ),
                    "sync_interval_seconds": 45.0,
                    "fee_tier": "Priority",
                }
            )

            page = SettingsPage(
                service,
                custom,
            )

            page.load_defaults()

            self.assertEqual(
                service.load(),
                custom,
            )

            self.assertEqual(
                page.fee_tier.currentText(),
                "Normal",
            )


if __name__ == "__main__":
    unittest.main()
