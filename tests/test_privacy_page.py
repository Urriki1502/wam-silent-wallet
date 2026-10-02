import os
os.environ.setdefault(
    "QT_QPA_PLATFORM",
    "offscreen",
)

import unittest

from PySide6.QtWidgets import QApplication

from wam_silent_wallet.pages.privacy_page import PrivacyPage


class _Cookie:
    def is_file(self):
        return True


class _DirectNode:
    rpc_url = "http://127.0.0.1:18443"
    cookie_path = _Cookie()

    def network_info(self):
        return {
            "networkactive": True,
            "networks": [
                {
                    "name": "ipv4",
                    "reachable": True,
                    "proxy": "",
                },
                {
                    "name": "onion",
                    "reachable": False,
                    "proxy": "",
                },
            ],
        }


class _TorNode:
    rpc_url = "http://127.0.0.1:18443"
    cookie_path = _Cookie()

    def network_info(self):
        return {
            "networkactive": True,
            "networks": [
                {
                    "name": "ipv4",
                    "reachable": True,
                    "proxy": "127.0.0.1:9050",
                },
                {
                    "name": "onion",
                    "reachable": True,
                    "proxy": "127.0.0.1:9050",
                },
            ],
        }


class PrivacyPageTests(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls):
        cls.app = (
            QApplication.instance()
            or QApplication([])
        )

    def test_direct_status_is_visible(self):
        page = PrivacyPage(
            _DirectNode()
        )

        self.assertEqual(
            page.mode_value.text(),
            "direct",
        )

        self.assertEqual(
            page.mode_badge.text(),
            "DIRECT",
        )

        self.assertIn(
            "CLEARNET_DIRECT",
            page.warning_text.text(),
        )

    def test_tor_ready_status_is_visible(self):
        page = PrivacyPage(
            _TorNode()
        )

        self.assertEqual(
            page.mode_value.text(),
            "tor_ready",
        )

        self.assertEqual(
            page.mode_badge.text(),
            "TOR READY",
        )

        self.assertEqual(
            page.onion_proxy_value.text(),
            "127.0.0.1:9050",
        )

        self.assertEqual(
            page.warning_text.text(),
            "Warnings: NONE",
        )


if __name__ == "__main__":
    unittest.main()
