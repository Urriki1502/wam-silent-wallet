from pathlib import Path
import unittest

from wam_silent_wallet.services.node_service import (
    NodeService,
)
from wam_silent_wallet.services.sync_service import (
    BackgroundSyncService,
)


class FakeStatus:
    def __init__(
        self,
        *,
        ready=True,
    ):
        self.network = type(
            "NetworkValue",
            (),
            {"value": "regtest"},
        )()

        self.blocks = 500
        self.headers = 500
        self.initial_download = not ready
        self.ready = ready
        self.tip = "a" * 64


class FailingClient:
    def status(self):
        raise ConnectionError(
            "connection refused"
        )


class NodeResilienceTests(
    unittest.TestCase
):
    def test_details_does_not_attest_when_node_not_ready(self):
        node = object.__new__(
            NodeService
        )

        node.rpc_url = (
            "http://127.0.0.1:18443"
        )

        node.cookie_path = Path(
            "/tmp/nonexistent-cookie"
        )

        node.snapshot = lambda: {
            "network": "regtest",
            "blocks": 500,
            "headers": 499,
            "ibd": False,
            "ready": False,
            "tip": "a" * 64,
        }

        def forbidden():
            raise AssertionError(
                "scanner_chain must not be called"
            )

        node.scanner_chain = forbidden

        info = node.details()

        self.assertFalse(
            info["ready"]
        )

        self.assertIsNone(
            info["mempool_transactions"]
        )

    def test_snapshot_transport_failure_is_normalized(self):
        node = object.__new__(
            NodeService
        )

        node.client = FailingClient()

        called = []

        node.reconnect = lambda: (
            called.append(True)
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "NODE_UNAVAILABLE",
        ):
            node.snapshot()

        self.assertEqual(
            called,
            [True],
        )

    def test_sdk_not_ready_is_normalized(self):
        node = object.__new__(
            NodeService
        )

        class Chain:
            def attest(self):
                raise ValueError(
                    "SDK_CHAIN_NOT_READY"
                )

        node._scanner_chain = Chain()

        called = []

        node.reconnect = lambda: (
            called.append(True)
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "NODE_NOT_READY",
        ):
            node.scanner_chain()

        self.assertEqual(
            called,
            [True],
        )


class RecoveringNode:
    def __init__(self):
        self.calls = 0

    def details(self):
        self.calls += 1

        if self.calls == 1:
            raise RuntimeError(
                "NODE_UNAVAILABLE"
            )

        return {
            "network": "regtest",
            "blocks": 500,
            "headers": 500,
            "ibd": False,
            "ready": True,
            "tip": "b" * 64,
            "mempool_transactions": 0,
            "tip_tx_count": 1,
            "tip_time": 1_700_000_000,
            "rpc_url": "http://127.0.0.1:18443",
            "cookie_exists": True,
        }

    def scanner_chain(self):
        return object()


class RecoveringWallet:
    def background_sync_snapshot(
        self,
        passphrase,
        chain,
    ):
        return {
            "scan_blocks": 0,
            "scan_transactions": 0,
            "scan_candidates": 0,
            "scan_rollback": 0,
            "confirmed_atoms": 100,
            "available_atoms": 100,
            "unconfirmed_atoms": 0,
            "pending_spent_atoms": 0,
            "payments_count": 1,
            "history_count": 1,
            "snapshot_fingerprint": "c" * 64,
            "payments": [],
        }


class SyncReconnectTests(
    unittest.TestCase
):
    def test_background_sync_recovers_after_node_failure(self):
        service = BackgroundSyncService(
            RecoveringWallet(),
            RecoveringNode(),
        )

        first = service.cycle(
            "secret"
        )

        self.assertEqual(
            first.status,
            "node_error",
        )

        self.assertEqual(
            first.error_code,
            "NODE_UNAVAILABLE",
        )

        self.assertEqual(
            first.consecutive_failures,
            1,
        )

        second = service.cycle(
            "secret"
        )

        self.assertEqual(
            second.status,
            "synced",
        )

        self.assertEqual(
            second.consecutive_failures,
            0,
        )


if __name__ == "__main__":
    unittest.main()
