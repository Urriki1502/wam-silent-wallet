import unittest

from wam_silent_wallet.services.signer_service import (
    LocalWspSignerBackend,
    SignerCapabilities,
    SignerService,
)


class FakeBackend:
    def __init__(
        self,
        result=b"signed-psbt",
    ):
        self.result = result
        self.calls = []

    @property
    def capabilities(self):
        return SignerCapabilities(
            backend_id="fake",
            local_private_keys=False,
            hardware_signing=True,
            secure_enclave=False,
        )

    def sign(
        self,
        *,
        keyring,
        proposal,
        approved_intents,
        approved_max_fee,
    ):
        self.calls.append(
            {
                "keyring": keyring,
                "proposal": proposal,
                "approved_intents": approved_intents,
                "approved_max_fee": approved_max_fee,
            }
        )

        return self.result


class SignerServiceTests(
    unittest.TestCase
):
    def test_default_backend_is_local_wsp(self):
        service = SignerService()

        self.assertIsInstance(
            service.backend,
            LocalWspSignerBackend,
        )

        self.assertEqual(
            service.capabilities.backend_id,
            "local_wsp",
        )

        self.assertTrue(
            service.capabilities.local_private_keys
        )

        self.assertFalse(
            service.capabilities.hardware_signing
        )

        self.assertFalse(
            service.capabilities.secure_enclave
        )

    def test_backend_boundary_receives_only_signing_inputs(self):
        backend = FakeBackend()
        service = SignerService(
            backend
        )

        keyring = object()
        proposal = object()
        intents = (
            object(),
            object(),
        )

        result = service.sign(
            keyring=keyring,
            proposal=proposal,
            approved_intents=intents,
            approved_max_fee=1234,
        )

        self.assertEqual(
            result,
            b"signed-psbt",
        )

        self.assertEqual(
            len(backend.calls),
            1,
        )

        call = backend.calls[0]

        self.assertIs(
            call["keyring"],
            keyring,
        )

        self.assertIs(
            call["proposal"],
            proposal,
        )

        self.assertEqual(
            call["approved_intents"],
            intents,
        )

        self.assertEqual(
            call["approved_max_fee"],
            1234,
        )

    def test_service_does_not_retain_signing_secrets(self):
        backend = FakeBackend()
        service = SignerService(
            backend
        )

        keyring = object()
        proposal = object()

        service.sign(
            keyring=keyring,
            proposal=proposal,
            approved_intents=(),
            approved_max_fee=1,
        )

        state = service.__dict__

        self.assertNotIn(
            "keyring",
            state,
        )

        self.assertNotIn(
            "proposal",
            state,
        )

        self.assertNotIn(
            "passphrase",
            state,
        )

    def test_rejects_invalid_inputs_before_backend(self):
        backend = FakeBackend()
        service = SignerService(
            backend
        )

        with self.assertRaisesRegex(
            ValueError,
            "SIGNER_KEYRING_REQUIRED",
        ):
            service.sign(
                keyring=None,
                proposal=object(),
                approved_intents=(),
                approved_max_fee=1,
            )

        with self.assertRaisesRegex(
            ValueError,
            "SIGNER_PROPOSAL_REQUIRED",
        ):
            service.sign(
                keyring=object(),
                proposal=None,
                approved_intents=(),
                approved_max_fee=1,
            )

        for value in (
            0,
            -1,
            True,
            1.5,
            "1",
        ):
            with self.subTest(
                approved_max_fee=value
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "SIGNER_FEE_APPROVAL",
                ):
                    service.sign(
                        keyring=object(),
                        proposal=object(),
                        approved_intents=(),
                        approved_max_fee=value,
                    )

        self.assertEqual(
            backend.calls,
            [],
        )

    def test_rejects_empty_or_non_bytes_backend_result(self):
        for result in (
            b"",
            bytearray(),
            None,
            "signed",
        ):
            with self.subTest(
                result=result
            ):
                service = SignerService(
                    FakeBackend(
                        result
                    )
                )

                with self.assertRaisesRegex(
                    ValueError,
                    "SIGNER_RESULT",
                ):
                    service.sign(
                        keyring=object(),
                        proposal=object(),
                        approved_intents=(),
                        approved_max_fee=1,
                    )

    def test_mutable_backend_result_is_copied_to_bytes(self):
        service = SignerService(
            FakeBackend(
                bytearray(
                    b"abc"
                )
            )
        )

        result = service.sign(
            keyring=object(),
            proposal=object(),
            approved_intents=(),
            approved_max_fee=1,
        )

        self.assertEqual(
            result,
            b"abc",
        )

        self.assertIsInstance(
            result,
            bytes,
        )


if __name__ == "__main__":
    unittest.main()
