import unittest

from wam_silent_wallet.services.privacy_service import NetworkPrivacyService


class _Cookie:
    def is_file(self):
        return True


class _FakeNode:
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


class NetworkPrivacyServiceTests(
    unittest.TestCase
):
    def test_snapshot_uses_read_only_node_bridge(self):
        result = NetworkPrivacyService(
            _FakeNode()
        ).snapshot()

        self.assertEqual(
            result.mode,
            "direct",
        )

        self.assertTrue(
            result.rpc_loopback
        )

        self.assertTrue(
            result.cookie_available
        )

    def test_direct_mode_detects_unproxied_clearnet(self):
        result = (
            NetworkPrivacyService
            .analyze(
                rpc_url="http://127.0.0.1:18443",
                cookie_available=True,
                network_info={
                    "networkactive": True,
                    "networks": [
                        {
                            "name": "ipv4",
                            "reachable": True,
                            "proxy": "",
                        },
                        {
                            "name": "ipv6",
                            "reachable": False,
                            "proxy": "",
                        },
                        {
                            "name": "onion",
                            "reachable": False,
                            "proxy": "",
                        },
                    ],
                },
            )
        )

        self.assertEqual(
            result.mode,
            "direct",
        )

        self.assertIn(
            "CLEARNET_DIRECT",
            result.warnings,
        )

        self.assertIn(
            "ONION_NOT_REACHABLE",
            result.warnings,
        )

    def test_mixed_mode_detects_onion_plus_direct_clearnet(self):
        result = (
            NetworkPrivacyService
            .analyze(
                rpc_url="http://127.0.0.1:18443",
                cookie_available=True,
                network_info={
                    "networkactive": True,
                    "networks": [
                        {
                            "name": "ipv4",
                            "reachable": True,
                            "proxy": "",
                        },
                        {
                            "name": "onion",
                            "reachable": True,
                            "proxy": "127.0.0.1:9050",
                        },
                    ],
                },
            )
        )

        self.assertEqual(
            result.mode,
            "tor_available_mixed",
        )

        self.assertEqual(
            result.onion_proxy,
            "127.0.0.1:9050",
        )

        self.assertIn(
            "CLEARNET_DIRECT",
            result.warnings,
        )

    def test_tor_ready_when_reachable_clearnet_is_proxy_routed(self):
        result = (
            NetworkPrivacyService
            .analyze(
                rpc_url="http://127.0.0.1:18443",
                cookie_available=True,
                network_info={
                    "networkactive": True,
                    "networks": [
                        {
                            "name": "ipv4",
                            "reachable": True,
                            "proxy": "127.0.0.1:9050",
                        },
                        {
                            "name": "ipv6",
                            "reachable": False,
                            "proxy": "",
                        },
                        {
                            "name": "onion",
                            "reachable": True,
                            "proxy": "127.0.0.1:9050",
                        },
                    ],
                },
            )
        )

        self.assertEqual(
            result.mode,
            "tor_ready",
        )

        self.assertTrue(
            result.clearnet_proxy_routed
        )

        self.assertNotIn(
            "CLEARNET_DIRECT",
            result.warnings,
        )

    def test_remote_rpc_is_flagged(self):
        result = (
            NetworkPrivacyService
            .analyze(
                rpc_url="http://192.168.1.20:18443",
                cookie_available=True,
                network_info={
                    "networks": [],
                },
            )
        )

        self.assertFalse(
            result.rpc_loopback
        )

        self.assertIn(
            "RPC_NOT_LOOPBACK",
            result.warnings,
        )

    def test_missing_cookie_is_flagged(self):
        result = (
            NetworkPrivacyService
            .analyze(
                rpc_url="http://127.0.0.1:18443",
                cookie_available=False,
                network_info={
                    "networks": [],
                },
            )
        )

        self.assertFalse(
            result.cookie_available
        )

        self.assertIn(
            "RPC_COOKIE_MISSING",
            result.warnings,
        )

    def test_direct_route_is_broadcast_safe(self):
        result = NetworkPrivacyService(
            _FakeNode()
        ).assert_broadcast_safe()

        self.assertEqual(
            result.mode,
            "direct",
        )

    def test_mixed_route_is_blocked_for_broadcast(self):
        class MixedNode(_FakeNode):
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
                            "reachable": True,
                            "proxy": "127.0.0.1:9050",
                        },
                    ],
                }

        with self.assertRaisesRegex(
            ValueError,
            "PRIVACY_ROUTE_AMBIGUOUS",
        ):
            NetworkPrivacyService(
                MixedNode()
            ).assert_broadcast_safe()

    def test_inactive_network_is_blocked_for_broadcast(self):
        class InactiveNode(_FakeNode):
            def network_info(self):
                return {
                    "networkactive": False,
                    "networks": [],
                }

        with self.assertRaisesRegex(
            ValueError,
            "PRIVACY_NETWORK_INACTIVE",
        ):
            NetworkPrivacyService(
                InactiveNode()
            ).assert_broadcast_safe()

    def test_invalid_network_payload_is_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "PRIVACY_NETWORK_INFO",
        ):
            NetworkPrivacyService.analyze(
                rpc_url="http://127.0.0.1:18443",
                cookie_available=True,
                network_info=[],
            )

        with self.assertRaisesRegex(
            ValueError,
            "PRIVACY_NETWORKS",
        ):
            NetworkPrivacyService.analyze(
                rpc_url="http://127.0.0.1:18443",
                cookie_available=True,
                network_info={
                    "networks": {},
                },
            )


if __name__ == "__main__":
    unittest.main()
