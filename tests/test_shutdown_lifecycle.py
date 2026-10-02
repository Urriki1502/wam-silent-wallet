from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from wam_silent_wallet.main_window import (
    MainWindow,
)
from wam_silent_wallet.services.wallet_service import (
    WalletService,
)


class FakeThread:
    def __init__(
        self,
        wait_result=True,
    ):
        self.wait_result = wait_result
        self.stop_calls = 0
        self.wait_calls = []

    def stop(self):
        self.stop_calls += 1

    def wait(
        self,
        timeout=None,
    ):
        self.wait_calls.append(
            timeout
        )

        if timeout is None:
            return True

        return self.wait_result


class FakeSession:
    def __init__(self):
        self.lock_calls = 0

    def lock(self):
        self.lock_calls += 1


class FakeRuntimeLock:
    def __init__(self):
        self.release_calls = 0

    def release(self):
        self.release_calls += 1


class FakeWallet:
    def __init__(self):
        self.integrity_calls = 0

    def validate_shutdown_integrity(self):
        self.integrity_calls += 1

        return {
            "wallet_exists": True,
            "database": "ok",
            "keys": "ok",
            "unresolved_payments": 0,
        }


class ShutdownLifecycleTests(
    unittest.TestCase
):
    def test_background_worker_is_joined_before_clear(self):
        worker = FakeThread(
            True
        )

        obj = SimpleNamespace(
            background_sync_thread=worker,
        )

        result = (
            MainWindow
            ._stop_background_sync(
                obj,
                timeout_ms=5000,
            )
        )

        self.assertTrue(
            result
        )

        self.assertEqual(
            worker.stop_calls,
            1,
        )

        self.assertEqual(
            worker.wait_calls,
            [5000],
        )

        self.assertIsNone(
            obj.background_sync_thread
        )

    def test_background_timeout_retains_worker(self):
        worker = FakeThread(
            False
        )

        obj = SimpleNamespace(
            background_sync_thread=worker,
        )

        result = (
            MainWindow
            ._stop_background_sync(
                obj,
                timeout_ms=10,
            )
        )

        self.assertFalse(
            result
        )

        self.assertIs(
            obj.background_sync_thread,
            worker,
        )

    def test_recovery_timeout_retains_worker(self):
        worker = FakeThread(
            False
        )

        obj = SimpleNamespace(
            recovery_thread=worker,
            recovery_worker=worker,
        )

        result = (
            MainWindow
            ._wait_for_recovery_shutdown(
                obj,
                timeout_ms=10,
            )
        )

        self.assertFalse(
            result
        )

        self.assertIs(
            obj.recovery_thread,
            worker,
        )

    def test_recovery_join_clears_references(self):
        worker = FakeThread(
            True
        )

        obj = SimpleNamespace(
            recovery_thread=worker,
            recovery_worker=worker,
        )

        result = (
            MainWindow
            ._wait_for_recovery_shutdown(
                obj,
                timeout_ms=5000,
            )
        )

        self.assertTrue(
            result
        )

        self.assertIsNone(
            obj.recovery_thread
        )

        self.assertIsNone(
            obj.recovery_worker
        )

    def test_finalize_is_idempotent_and_releases_lock(self):
        session = FakeSession()
        runtime = FakeRuntimeLock()
        wallet = FakeWallet()

        obj = SimpleNamespace(
            _shutdown_complete=False,
            session_service=session,
            runtime_lock=runtime,
            wallet_service=wallet,
        )

        MainWindow._finalize_shutdown(
            obj
        )

        MainWindow._finalize_shutdown(
            obj
        )

        self.assertTrue(
            obj._shutdown_complete
        )

        self.assertEqual(
            session.lock_calls,
            1,
        )

        self.assertEqual(
            wallet.integrity_calls,
            1,
        )

        self.assertEqual(
            runtime.release_calls,
            1,
        )


class ShutdownIntegrityTests(
    unittest.TestCase
):
    def test_shutdown_integrity_runs_all_preflights(self):
        obj = object.__new__(
            WalletService
        )

        tmp = (
            tempfile
            .TemporaryDirectory()
        )

        self.addCleanup(
            tmp.cleanup
        )

        root = Path(
            tmp.name
        )

        obj.db_path = (
            root / "wallet.db"
        )

        obj.keys_path = (
            root / "keys.wsp"
        )

        obj.db_path.write_bytes(
            b"x"
        )

        obj.keys_path.write_bytes(
            b"x"
        )

        calls = []

        obj._validate_startup_fileset = (
            lambda: calls.append(
                "fileset"
            )
        )

        obj._validate_database_preflight = (
            lambda: calls.append(
                "database"
            )
        )

        obj._validate_keys_preflight = (
            lambda: calls.append(
                "keys"
            )
        )

        obj.payment_journal = (
            SimpleNamespace(
                unresolved=lambda: [
                    {"state": "signed"}
                ]
            )
        )

        result = (
            WalletService
            .validate_shutdown_integrity(
                obj
            )
        )

        self.assertEqual(
            calls,
            [
                "fileset",
                "database",
                "keys",
            ],
        )

        self.assertEqual(
            result[
                "unresolved_payments"
            ],
            1,
        )


if __name__ == "__main__":
    unittest.main()
