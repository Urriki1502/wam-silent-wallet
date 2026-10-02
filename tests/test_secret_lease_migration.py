from contextlib import contextmanager
import unittest

from wam_silent_wallet.services.wallet_service import WalletService
from wam_silent_wallet.services.sync_worker import BackgroundSyncThread


class _Outcome:
    next_delay_seconds = 0


class _FakeSyncService:
    def __init__(self):
        self.secrets = []

    def cycle(self, secret):
        self.secrets.append(secret)
        return _Outcome()


class _FakeSessionService:
    def __init__(self):
        self.calls = 0
        self.last_lease = None

    @contextmanager
    def secret_lease(self):
        self.calls += 1

        if self.calls > 1:
            raise ValueError("SESSION_LOCKED")

        lease = bytearray(b"0123456789ab")
        self.last_lease = lease

        try:
            yield lease
        finally:
            for index in range(len(lease)):
                lease[index] = 0


class SecretLeaseMigrationTests(unittest.TestCase):
    def test_wallet_accepts_mutable_secret_material(self):
        secret = bytearray(b"0123456789ab")

        value = WalletService._password_bytes(secret)

        self.assertEqual(
            value,
            b"0123456789ab",
        )

        self.assertIsInstance(
            value,
            bytes,
        )

    def test_wallet_rejects_invalid_secret_types(self):
        for value in (None, 123, object(), bytearray()):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    ValueError,
                    "PASSPHRASE_REQUIRED",
                ):
                    WalletService._password_bytes(value)

    def test_background_sync_uses_secret_lease(self):
        sync = _FakeSyncService()
        session = _FakeSessionService()

        worker = BackgroundSyncThread(
            sync,
            session,
        )

        worker.run()

        self.assertEqual(
            len(sync.secrets),
            1,
        )

        self.assertIs(
            sync.secrets[0],
            session.last_lease,
        )

        self.assertEqual(
            session.last_lease,
            bytearray(
                len(session.last_lease)
            ),
        )


if __name__ == "__main__":
    unittest.main()
