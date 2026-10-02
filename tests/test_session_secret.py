import unittest

from wam_silent_wallet.services.session_service import SessionService


class FakeWalletService:
    def __init__(self):
        self.seen = []

    def verify_passphrase(
        self,
        passphrase,
    ):
        self.seen.append(
            passphrase
        )

        return {
            "valid": True,
            "address": "wamrtsp1example",
            "accounts": 1,
        }


class SessionSecretLeaseTests(
    unittest.TestCase
):
    def setUp(self):
        self.wallet = FakeWalletService()

        self.session = SessionService(
            self.wallet
        )

        self.session.unlock(
            "correct horse battery staple"
        )

    def tearDown(self):
        self.session.lock()

    def test_unlock_stores_mutable_secret_not_plaintext_attribute(self):
        self.assertTrue(
            self.session.unlocked
        )

        self.assertIsInstance(
            self.session._passphrase,
            bytearray,
        )

        self.assertNotIn(
            "correct horse battery staple",
            self.session.__dict__.values(),
        )

    def test_secret_lease_returns_mutable_copy(self):
        with self.session.secret_lease() as secret:
            self.assertIsInstance(
                secret,
                bytearray,
            )

            self.assertEqual(
                bytes(secret),
                b"correct horse battery staple",
            )

            self.assertIsNot(
                secret,
                self.session._passphrase,
            )

    def test_secret_lease_is_zeroized_after_context_exit(self):
        leased = None

        with self.session.secret_lease() as secret:
            leased = secret

        self.assertIsNotNone(
            leased
        )

        self.assertEqual(
            leased,
            bytearray(
                len(leased)
            ),
        )

        self.assertTrue(
            self.session.unlocked
        )

    def test_each_lease_is_independent(self):
        with self.session.secret_lease() as first:
            first_id = id(first)

        with self.session.secret_lease() as second:
            second_id = id(second)

            self.assertEqual(
                bytes(second),
                b"correct horse battery staple",
            )

        self.assertNotEqual(
            first_id,
            second_id,
        )

    def test_locked_session_refuses_secret_lease(self):
        self.session.lock()

        with self.assertRaisesRegex(
            ValueError,
            "SESSION_LOCKED",
        ):
            with self.session.secret_lease():
                pass

    def test_lock_zeroizes_session_storage(self):
        original = self.session._passphrase

        self.session.lock()

        self.assertFalse(
            self.session.unlocked
        )

        self.assertEqual(
            original,
            bytearray(
                len(original)
            ),
        )

        self.assertIsNone(
            self.session._passphrase
        )

    def test_public_identity_is_not_secret(self):
        identity = (
            self.session
            .public_identity
        )

        self.assertEqual(
            identity["accounts"],
            1,
        )

        self.assertNotIn(
            "correct horse battery staple",
            repr(identity),
        )


if __name__ == "__main__":
    unittest.main()
