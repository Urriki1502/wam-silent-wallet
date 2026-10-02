from pathlib import Path
import tempfile
import unittest

from wam_silent_wallet.services.config_service import ConfigService
from wam_silent_wallet.services.node_service import NodeService
from wam_silent_wallet.services.sync_service import BackgroundSyncService


class DummyWallet:
    pass


class DummyNode:
    pass


class RuntimeConfigIntegrationTests(unittest.TestCase):
    def test_load_or_create_persists_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            service = ConfigService(path)

            config = service.load_or_create()

            self.assertTrue(path.is_file())
            self.assertEqual(config.network, "regtest")
            self.assertEqual(config.fee_tier, "Normal")
            self.assertEqual(config.sync_interval_seconds, 15.0)

            self.assertEqual(
                service.load(),
                config,
            )

    def test_node_service_uses_runtime_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            cookie = Path(tmp) / ".cookie"
            config = ConfigService.validate(
                {
                    "version": 1,
                    "network": "regtest",
                    "rpc_url": "http://127.0.0.1:19443",
                    "cookie_path": str(cookie),
                    "sync_interval_seconds": 30.0,
                    "fee_tier": "Priority",
                }
            )

            node = NodeService.from_runtime_config(config)

            self.assertEqual(
                node.rpc_url,
                "http://127.0.0.1:19443",
            )
            self.assertEqual(
                node.cookie_path,
                cookie,
            )

    def test_background_sync_uses_configured_interval(self):
        service = BackgroundSyncService(
            DummyWallet(),
            DummyNode(),
            success_interval_seconds=30.0,
        )

        self.assertEqual(
            service.success_interval_seconds,
            30.0,
        )

    def test_background_sync_rejects_bad_interval(self):
        for value in (0, 1.9, 301, True, "15"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    ValueError,
                    "CONFIG_SYNC_INTERVAL",
                ):
                    BackgroundSyncService(
                        DummyWallet(),
                        DummyNode(),
                        success_interval_seconds=value,
                    )


if __name__ == "__main__":
    unittest.main()
