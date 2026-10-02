import json
import os
from pathlib import Path
import tempfile
import unittest

from wam_silent_wallet.services.config_service import (
    ConfigService,
    RuntimeConfig,
)


class ConfigServiceTests(
    unittest.TestCase
):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()

        self.path = (
            Path(self.temp.name)
            / "config.json"
        )

        self.service = ConfigService(
            self.path
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_missing_file_returns_safe_defaults(self):
        config = self.service.load()

        self.assertEqual(
            config.version,
            1,
        )

        self.assertEqual(
            config.network,
            "regtest",
        )

        self.assertEqual(
            config.rpc_url,
            "http://127.0.0.1:18443",
        )

        self.assertEqual(
            config.fee_tier,
            "Normal",
        )

        self.assertEqual(
            config.sync_interval_seconds,
            15.0,
        )

        self.assertFalse(
            self.path.exists()
        )

    def test_round_trip_and_atomic_save(self):
        saved = self.service.update(
            rpc_url="http://localhost:19443",
            sync_interval_seconds=30,
            fee_tier="Priority",
        )

        loaded = self.service.load()

        self.assertEqual(
            saved,
            loaded,
        )

        self.assertEqual(
            loaded.rpc_url,
            "http://localhost:19443",
        )

        self.assertEqual(
            loaded.sync_interval_seconds,
            30.0,
        )

        self.assertEqual(
            loaded.fee_tier,
            "Priority",
        )

        payload = json.loads(
            self.path.read_text(
                encoding="utf-8"
            )
        )

        self.assertNotIn(
            "passphrase",
            payload,
        )

        self.assertNotIn(
            "private_key",
            payload,
        )

        leftovers = list(
            self.path.parent.glob(
                ".config.*.tmp"
            )
        )

        self.assertEqual(
            leftovers,
            [],
        )

    def test_file_permissions_are_private_when_supported(self):
        self.service.save(
            self.service.defaults()
        )

        mode = (
            os.stat(
                self.path
            ).st_mode
            & 0o777
        )

        self.assertEqual(
            mode,
            0o600,
        )

    def test_rejects_non_regtest_network(self):
        config = self.service.defaults()

        with self.assertRaisesRegex(
            ValueError,
            "CONFIG_NETWORK",
        ):
            self.service.save(
                {
                    **config.__dict__,
                    "network": "main",
                }
            )

    def test_rejects_remote_or_credentialed_rpc(self):
        config = self.service.defaults()

        for rpc_url in (
            "http://192.168.1.20:18443",
            "http://user:pass@127.0.0.1:18443",
            "https://127.0.0.1:18443",
            "http://127.0.0.1:18443/path",
        ):
            with self.subTest(
                rpc_url=rpc_url
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "CONFIG_RPC_URL",
                ):
                    self.service.save(
                        {
                            **config.__dict__,
                            "rpc_url": rpc_url,
                        }
                    )

    def test_rejects_bad_sync_interval(self):
        config = self.service.defaults()

        for interval in (
            0,
            1.99,
            301,
            True,
            "15",
        ):
            with self.subTest(
                interval=interval
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "CONFIG_SYNC_INTERVAL",
                ):
                    self.service.save(
                        {
                            **config.__dict__,
                            "sync_interval_seconds": interval,
                        }
                    )

    def test_rejects_unknown_fee_tier(self):
        config = self.service.defaults()

        with self.assertRaisesRegex(
            ValueError,
            "CONFIG_FEE_TIER",
        ):
            self.service.save(
                {
                    **config.__dict__,
                    "fee_tier": "Turbo",
                }
            )

    def test_rejects_relative_cookie_path(self):
        config = self.service.defaults()

        with self.assertRaisesRegex(
            ValueError,
            "CONFIG_COOKIE_PATH",
        ):
            self.service.save(
                {
                    **config.__dict__,
                    "cookie_path": "relative/.cookie",
                }
            )

    def test_rejects_corrupt_file(self):
        self.path.write_text(
            "{broken",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            ValueError,
            "CONFIG_READ",
        ):
            self.service.load()

    def test_rejects_unknown_fields(self):
        config = self.service.defaults()

        with self.assertRaisesRegex(
            ValueError,
            "CONFIG_FIELDS",
        ):
            self.service.save(
                {
                    **config.__dict__,
                    "unexpected": "value",
                }
            )


if __name__ == "__main__":
    unittest.main()
