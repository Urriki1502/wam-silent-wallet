import threading
import unittest

from wam_silent_wallet.services.sync_service import BackgroundSyncService


class FakeClock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        self.value += 0.25
        return self.value


class FakeNode:
    def __init__(
        self,
        *,
        ready=True,
        fail=None,
    ):
        self.ready = ready
        self.fail = fail
        self.snapshot_calls = 0
        self.details_calls = 0
        self.chain_calls = 0

    def snapshot(self):
        self.snapshot_calls += 1

        if self.fail is not None:
            raise self.fail

        return {
            "network": "regtest",
            "blocks": 335,
            "headers": 335,
            "ibd": not self.ready,
            "ready": self.ready,
            "tip": "a" * 64,
        }

    def details(self):
        self.details_calls += 1

        return {
            **self.snapshot(),
            "mempool_transactions": 0,
            "tip_tx_count": 1,
            "tip_time": 1_700_000_000,
            "rpc_url": "http://127.0.0.1:18443",
            "cookie_exists": True,
        }

    def scanner_chain(self):
        self.chain_calls += 1
        return object()


class FakeWallet:
    def __init__(
        self,
        *,
        fail=None,
    ):
        self.fail = fail
        self.calls = 0
        self.seen_passphrases = []

    def background_sync_snapshot(
        self,
        passphrase,
        chain,
    ):
        self.calls += 1
        self.seen_passphrases.append(
            passphrase
        )

        if self.fail is not None:
            raise self.fail

        return {
            "scan_blocks": 1,
            "scan_transactions": 1,
            "scan_candidates": 1,
            "scan_rollback": 0,
            "confirmed_atoms": 100,
            "available_atoms": 100,
            "unconfirmed_atoms": 0,
            "pending_spent_atoms": 0,
            "payments_count": 2,
            "history_count": 2,
            "payments": [],
        }


class BackgroundSyncServiceTests(
    unittest.TestCase
):
    def test_success_resets_failures_and_detects_changes(self):
        clock = FakeClock()
        node = FakeNode()
        wallet = FakeWallet()

        service = BackgroundSyncService(
            wallet,
            node,
            clock=clock,
        )

        first = service.cycle(
            "correct horse battery staple"
        )

        self.assertEqual(
            first.status,
            "synced",
        )

        self.assertTrue(
            first.changed
        )

        self.assertEqual(
            first.consecutive_failures,
            0,
        )

        self.assertEqual(
            first.next_delay_seconds,
            15.0,
        )

        second = service.cycle(
            "correct horse battery staple"
        )

        self.assertEqual(
            second.status,
            "synced",
        )

        self.assertFalse(
            second.changed
        )

        self.assertNotIn(
            "passphrase",
            service.__dict__,
        )

        self.assertNotIn(
            "correct horse battery staple",
            repr(service.__dict__),
        )

    def test_accepts_mutable_secret_lease(self):
        clock = FakeClock()
        node = FakeNode()
        wallet = FakeWallet()

        service = BackgroundSyncService(
            wallet,
            node,
            clock=clock,
        )

        secret = bytearray(
            b"correct horse battery staple"
        )

        result = service.cycle(
            secret
        )

        self.assertEqual(
            result.status,
            "synced",
        )

        self.assertIs(
            wallet.seen_passphrases[0],
            secret,
        )

    def test_empty_mutable_secret_is_locked(self):
        service = BackgroundSyncService(
            FakeWallet(),
            FakeNode(),
            clock=FakeClock(),
        )

        result = service.cycle(
            bytearray()
        )

        self.assertEqual(
            result.status,
            "locked",
        )

        self.assertEqual(
            result.error_code,
            "SESSION_LOCKED",
        )

    def test_node_not_ready_uses_exponential_backoff(self):
        clock = FakeClock()
        node = FakeNode(
            ready=False
        )
        wallet = FakeWallet()

        service = BackgroundSyncService(
            wallet,
            node,
            clock=clock,
        )

        one = service.cycle(
            "pw"
        )

        two = service.cycle(
            "pw"
        )

        self.assertEqual(
            one.status,
            "node_not_ready",
        )

        self.assertEqual(
            one.next_delay_seconds,
            2.0,
        )

        self.assertEqual(
            two.next_delay_seconds,
            4.0,
        )

        self.assertEqual(
            wallet.calls,
            0,
        )

    def test_scanner_busy_is_transient_not_failure(self):
        clock = FakeClock()
        node = FakeNode()
        wallet = FakeWallet(
            fail=ValueError(
                "SCANNER_BUSY"
            )
        )

        service = BackgroundSyncService(
            wallet,
            node,
            clock=clock,
        )

        result = service.cycle(
            "pw"
        )

        self.assertEqual(
            result.status,
            "scanner_busy",
        )

        self.assertEqual(
            result.error_code,
            "SCANNER_BUSY",
        )

        self.assertEqual(
            result.consecutive_failures,
            0,
        )

        self.assertEqual(
            result.next_delay_seconds,
            2.0,
        )

    def test_generic_error_does_not_expose_message(self):
        clock = FakeClock()
        node = FakeNode()
        wallet = FakeWallet(
            fail=RuntimeError(
                "private internal details here"
            )
        )

        service = BackgroundSyncService(
            wallet,
            node,
            clock=clock,
        )

        result = service.cycle(
            "pw"
        )

        self.assertEqual(
            result.status,
            "wallet_error",
        )

        self.assertEqual(
            result.error_code,
            "RuntimeError",
        )

        self.assertNotIn(
            "private internal details here",
            repr(result),
        )

    def test_overlapping_cycle_is_rejected(self):
        clock = FakeClock()
        node = FakeNode()
        wallet = FakeWallet()

        service = BackgroundSyncService(
            wallet,
            node,
            clock=clock,
        )

        acquired = service._cycle_lock.acquire(
            blocking=False
        )

        self.assertTrue(
            acquired
        )

        try:
            result = service.cycle(
                "pw"
            )
        finally:
            service._cycle_lock.release()

        self.assertEqual(
            result.status,
            "cycle_busy",
        )

        self.assertEqual(
            result.error_code,
            "SYNC_CYCLE_BUSY",
        )

    def test_locked_session_short_circuits(self):
        clock = FakeClock()
        node = FakeNode()
        wallet = FakeWallet()

        service = BackgroundSyncService(
            wallet,
            node,
            clock=clock,
        )

        result = service.cycle(
            ""
        )

        self.assertEqual(
            result.status,
            "locked",
        )

        self.assertEqual(
            node.snapshot_calls,
            0,
        )

        self.assertEqual(
            wallet.calls,
            0,
        )

    def test_reset_clears_runtime_state(self):
        clock = FakeClock()
        service = BackgroundSyncService(
            FakeWallet(),
            FakeNode(
                ready=False
            ),
            clock=clock,
        )

        service.cycle(
            "pw"
        )

        self.assertEqual(
            service.consecutive_failures,
            1,
        )

        service.reset()

        self.assertEqual(
            service.consecutive_failures,
            0,
        )

        self.assertIsNone(
            service.last_success_monotonic
        )


if __name__ == "__main__":
    unittest.main()
