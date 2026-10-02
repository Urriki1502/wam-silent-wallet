from dataclasses import replace
import unittest

from wam_sp.psbt import (
    PSBT,
    Tx,
)
from wam_sp.wallet import (
    Intent,
    Proposal,
)

from wam_silent_wallet.services.signer_service import (
    LocalWspPreparer,
    LocalWspSignerBackend,
    SignerCapabilities,
    SignerService,
)
from wam_silent_wallet.services.transaction_manifest import (
    SigningManifest,
)


PUBKEY = (
    "79be667ef9dcbbac55a06295ce870b070"
    "29bfcdb2dce28d959f2815b16f81798"
)

_UNSET = object()


def make_proposal():
    return Proposal(
        coins=(
            {
                "txid": "11" * 32,
                "vout": 1,
                "account": "account-1",
                "epoch": 0,
                "atoms": 6_000_310,
                "public_key": PUBKEY,
                "tweak": "33" * 32,
                "label": 0,
                "k": 7,
            },
        ),
        intents=(
            Intent(
                "wamrtsp1example",
                1_000_000,
            ),
        ),
        fee=310,
        change_epoch=0,
        token="draft-token",
    )


def make_prepared_psbt():
    proposal = make_proposal()

    input_script = (
        b"\x51\x20"
        + bytes.fromhex(
            PUBKEY
        )
    )

    output_script = (
        b"\x51\x20"
        + bytes.fromhex(
            PUBKEY
        )
    )

    tx = Tx(
        inputs=(
            (
                proposal.coins[0]["txid"],
                proposal.coins[0]["vout"],
            ),
        ),
        outputs=(
            (
                1_000_000,
                output_script,
            ),
            (
                5_000_000,
                output_script,
            ),
        ),
    )

    return PSBT(
        tx=tx,
        utxos=(
            (
                6_000_310,
                input_script,
            ),
        ),
    ).encode()


def make_signed_psbt(
    prepared_psbt,
):
    psbt = PSBT.decode(
        prepared_psbt
    )

    return replace(
        psbt,
        signatures=(
            b"\x44" * 64,
        ),
    ).encode()


class FakePreparer:
    def __init__(
        self,
        result=None,
    ):
        self.result = (
            make_prepared_psbt()
            if result is None
            else result
        )

        self.calls = []

    def prepare(
        self,
        *,
        keyring,
        proposal,
    ):
        self.calls.append(
            {
                "keyring": keyring,
                "proposal": proposal,
            }
        )

        return self.result


class FakeBackend:
    def __init__(
        self,
        result=_UNSET,
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
        prepared_psbt,
        approved_intents,
        approved_max_fee,
    ):
        self.calls.append(
            {
                "keyring": keyring,
                "proposal": proposal,
                "prepared_psbt": (
                    prepared_psbt
                ),
                "approved_intents": (
                    approved_intents
                ),
                "approved_max_fee": (
                    approved_max_fee
                ),
            }
        )

        if self.result is _UNSET:
            return make_signed_psbt(
                prepared_psbt
            )

        return self.result


class SignerServiceTests(
    unittest.TestCase
):
    def test_default_backend_and_preparer(self):
        service = SignerService()

        self.assertIsInstance(
            service.backend,
            LocalWspSignerBackend,
        )

        self.assertIsInstance(
            service.preparer,
            LocalWspPreparer,
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

    def test_backend_boundary_receives_frozen_psbt(self):
        backend = FakeBackend()
        preparer = FakePreparer()

        service = SignerService(
            backend=backend,
            preparer=preparer,
        )

        keyring = object()
        proposal = make_proposal()

        manifest = (
            SigningManifest
            .from_proposal(
                proposal
            )
        )

        result = service.sign(
            keyring=keyring,
            proposal=proposal,
            approval_manifest=manifest,
            approved_intents=(
                proposal.intents
            ),
            approved_max_fee=310,
        )

        self.assertEqual(
            result,
            make_signed_psbt(
                preparer.result
            ),
        )

        self.assertEqual(
            len(preparer.calls),
            1,
        )

        self.assertIs(
            preparer.calls[0][
                "keyring"
            ],
            keyring,
        )

        self.assertIs(
            preparer.calls[0][
                "proposal"
            ],
            proposal,
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
            call["prepared_psbt"],
            preparer.result,
        )

        self.assertEqual(
            call["approved_intents"],
            proposal.intents,
        )

        self.assertEqual(
            call["approved_max_fee"],
            310,
        )

    def test_service_does_not_retain_signing_secrets(self):
        backend = FakeBackend()
        preparer = FakePreparer()

        service = SignerService(
            backend=backend,
            preparer=preparer,
        )

        keyring = object()
        proposal = make_proposal()

        manifest = (
            SigningManifest
            .from_proposal(
                proposal
            )
        )

        service.sign(
            keyring=keyring,
            proposal=proposal,
            approval_manifest=manifest,
            approved_intents=(
                proposal.intents
            ),
            approved_max_fee=310,
        )

        state = service.__dict__

        for forbidden in (
            "keyring",
            "proposal",
            "passphrase",
            "prepared_psbt",
            "manifest",
        ):
            self.assertNotIn(
                forbidden,
                state,
            )

    def test_rejects_invalid_inputs_before_backend(self):
        backend = FakeBackend()
        preparer = FakePreparer()

        service = SignerService(
            backend=backend,
            preparer=preparer,
        )

        proposal = make_proposal()

        manifest = (
            SigningManifest
            .from_proposal(
                proposal
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "SIGNER_KEYRING_REQUIRED",
        ):
            service.sign(
                keyring=None,
                proposal=proposal,
                approval_manifest=manifest,
                approved_intents=(
                    proposal.intents
                ),
                approved_max_fee=310,
            )

        with self.assertRaisesRegex(
            ValueError,
            "SIGNER_PROPOSAL_REQUIRED",
        ):
            service.sign(
                keyring=object(),
                proposal=None,
                approval_manifest=manifest,
                approved_intents=(),
                approved_max_fee=310,
            )

        with self.assertRaisesRegex(
            ValueError,
            "SIGNER_MANIFEST_REQUIRED",
        ):
            service.sign(
                keyring=object(),
                proposal=proposal,
                approval_manifest=None,
                approved_intents=(
                    proposal.intents
                ),
                approved_max_fee=310,
            )

        for value in (
            0,
            -1,
            True,
            1.5,
            "310",
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
                        proposal=proposal,
                        approval_manifest=(
                            manifest
                        ),
                        approved_intents=(
                            proposal.intents
                        ),
                        approved_max_fee=value,
                    )

        self.assertEqual(
            backend.calls,
            [],
        )

    def test_manifest_mismatch_stops_before_preparer(self):
        backend = FakeBackend()
        preparer = FakePreparer()

        service = SignerService(
            backend=backend,
            preparer=preparer,
        )

        proposal = make_proposal()

        manifest = (
            SigningManifest
            .from_proposal(
                proposal
            )
        )

        proposal.coins[0][
            "atoms"
        ] += 1

        with self.assertRaisesRegex(
            ValueError,
            "SIGNING_MANIFEST_MISMATCH",
        ):
            service.sign(
                keyring=object(),
                proposal=proposal,
                approval_manifest=manifest,
                approved_intents=(
                    proposal.intents
                ),
                approved_max_fee=310,
            )

        self.assertEqual(
            preparer.calls,
            [],
        )

        self.assertEqual(
            backend.calls,
            [],
        )

    def test_rejects_empty_or_non_bytes_backend_result(self):
        proposal = make_proposal()

        manifest = (
            SigningManifest
            .from_proposal(
                proposal
            )
        )

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
                    backend=FakeBackend(
                        result
                    ),
                    preparer=FakePreparer(),
                )

                with self.assertRaisesRegex(
                    ValueError,
                    "SIGNER_RESULT",
                ):
                    service.sign(
                        keyring=object(),
                        proposal=proposal,
                        approval_manifest=(
                            manifest
                        ),
                        approved_intents=(
                            proposal.intents
                        ),
                        approved_max_fee=310,
                    )

    def test_mutable_backend_result_is_copied_to_bytes(self):
        proposal = make_proposal()

        manifest = (
            SigningManifest
            .from_proposal(
                proposal
            )
        )

        prepared = (
            make_prepared_psbt()
        )

        signed = (
            make_signed_psbt(
                prepared
            )
        )

        service = SignerService(
            backend=FakeBackend(
                bytearray(
                    signed
                )
            ),
            preparer=FakePreparer(
                prepared
            ),
        )

        result = service.sign(
            keyring=object(),
            proposal=proposal,
            approval_manifest=manifest,
            approved_intents=(
                proposal.intents
            ),
            approved_max_fee=310,
        )

        self.assertEqual(
            result,
            signed,
        )

        self.assertIsInstance(
            result,
            bytes,
        )


if __name__ == "__main__":
    unittest.main()
