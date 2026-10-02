import unittest

from wam_sp.wallet import (
    Intent,
    Proposal,
)

from wam_silent_wallet.services.payment_service import (
    PaymentReview,
    PaymentService,
)
from wam_silent_wallet.services.transaction_manifest import (
    SigningManifest,
)
from wam_silent_wallet.services.wallet_service import (
    WalletService,
)


class FakeRing:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeCoordinator:
    def __init__(self):
        self.mark_signed_calls = []
        self.release_calls = []
        self.state = "draft"

    def mark_signed(
        self,
        token,
    ):
        if self.state != "draft":
            raise ValueError(
                "RESERVATION_NOT_DRAFT"
            )

        self.mark_signed_calls.append(
            token
        )

        self.state = "signed"

    def release_draft(
        self,
        token,
    ):
        if self.state != "draft":
            raise ValueError(
                "RESERVATION_NOT_DRAFT"
            )

        self.release_calls.append(
            token
        )


class FakeWallet:
    def __init__(self):
        self.closed = False
        self.scan_calls = []
        self.broadcast_calls = []
        self.wallet = FakeCoordinator()

    def scan(
        self,
        chain,
        mempool=False,
    ):
        self.scan_calls.append(
            (chain, mempool)
        )

    def broadcast(
        self,
        signed_psbt,
        token,
        chain,
    ):
        self.broadcast_calls.append(
            (
                signed_psbt,
                token,
                chain,
            )
        )

        return "ab" * 32

    def close(self):
        self.closed = True


class FakeWalletService:
    def __init__(
        self,
        ring,
        wallet,
    ):
        self.ring = ring
        self.wallet = wallet
        self.open_calls = []

    def _open(
        self,
        passphrase,
    ):
        self.open_calls.append(
            passphrase
        )

        return (
            self.ring,
            self.wallet,
        )


class FakeNodeService:
    def __init__(self):
        self.scan_chain = object()
        self.send_chain = object()

    def scanner_chain(self):
        return self.scan_chain

    def broadcast_chain(self):
        return self.send_chain


class FakeSignerService:
    def __init__(
        self,
        mutate_proposal=False,
    ):
        self.calls = []
        self.mutate_proposal = (
            mutate_proposal
        )

    def sign(
        self,
        *,
        keyring,
        proposal,
        approval_manifest,
        approved_intents,
        approved_max_fee,
    ):
        self.calls.append(
            {
                "keyring": keyring,
                "proposal": proposal,
                "approval_manifest": (
                    approval_manifest
                ),
                "approved_intents": (
                    approved_intents
                ),
                "approved_max_fee": (
                    approved_max_fee
                ),
            }
        )

        if self.mutate_proposal:
            proposal.coins[0][
                "atoms"
            ] += 1

        return b"signed-psbt"

def make_proposal():
    return Proposal(
        coins=(
            {
                "txid": "11" * 32,
                "vout": 1,
                "account": "account-1",
                "epoch": 0,
                "atoms": 6_000_310,
                "public_key": "22" * 32,
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


def make_review(
    proposal=None,
    *,
    fee_atoms=310,
):
    if proposal is None:
        proposal = make_proposal()

    return PaymentReview(
        proposal=proposal,
        manifest=(
            SigningManifest
            .from_proposal(
                proposal
            )
        ),
        destination="wamrtsp1example",
        amount_atoms=1_000_000,
        fee_atoms=fee_atoms,
        fee_rate_atoms_vb=2,
        estimated_vsize=155,
        input_count=1,
        output_count=2,
        change_atoms=5_000_000,
        tier="Normal",
        fee_source="test",
    )


class PaymentSignerIntegrationTests(
    unittest.TestCase
):
    def test_broadcast_delegates_to_signer_boundary(self):
        ring = FakeRing()
        wallet = FakeWallet()

        wallet_service = (
            FakeWalletService(
                ring,
                wallet,
            )
        )

        node_service = (
            FakeNodeService()
        )

        signer_service = (
            FakeSignerService()
        )

        service = PaymentService(
            wallet_service,
            node_service,
            signer_service=signer_service,
        )

        review = make_review()

        result = service.broadcast(
            "secret",
            review,
        )

        self.assertEqual(
            wallet_service.open_calls,
            ["secret"],
        )

        self.assertEqual(
            wallet.scan_calls,
            [
                (
                    node_service.scan_chain,
                    True,
                )
            ],
        )

        self.assertEqual(
            len(signer_service.calls),
            1,
        )

        call = signer_service.calls[0]

        self.assertIs(
            call["keyring"],
            ring,
        )

        self.assertIs(
            call["proposal"],
            review.proposal,
        )

        self.assertIs(
            call["approval_manifest"],
            review.manifest,
        )

        self.assertEqual(
            call["approved_intents"],
            review.proposal.intents,
        )

        self.assertEqual(
            call["approved_max_fee"],
            310,
        )

        self.assertEqual(
            wallet.wallet.mark_signed_calls,
            ["draft-token"],
        )

        self.assertEqual(
            wallet.broadcast_calls,
            [
                (
                    b"signed-psbt",
                    "draft-token",
                    node_service.send_chain,
                )
            ],
        )

        self.assertEqual(
            result["txid"],
            "ab" * 32,
        )

        self.assertEqual(
            result[
                "signing_manifest"
            ],
            review.manifest.digest,
        )

        self.assertTrue(
            wallet.closed
        )

        self.assertTrue(
            ring.closed
        )

    def test_proposal_mutation_before_signing_fails_closed(self):
        ring = FakeRing()
        wallet = FakeWallet()
        signer = FakeSignerService()

        service = PaymentService(
            FakeWalletService(
                ring,
                wallet,
            ),
            FakeNodeService(),
            signer_service=signer,
        )

        review = make_review()

        review.proposal.coins[0][
            "atoms"
        ] += 1

        with self.assertRaisesRegex(
            ValueError,
            "SIGNING_MANIFEST_MISMATCH",
        ):
            service.broadcast(
                "secret",
                review,
            )

        self.assertEqual(
            signer.calls,
            [],
        )

        self.assertEqual(
            wallet.broadcast_calls,
            [],
        )

    def test_signer_mutation_is_detected_before_broadcast(self):
        ring = FakeRing()
        wallet = FakeWallet()

        signer = FakeSignerService(
            mutate_proposal=True,
        )

        service = PaymentService(
            FakeWalletService(
                ring,
                wallet,
            ),
            FakeNodeService(),
            signer_service=signer,
        )

        review = make_review()

        with self.assertRaisesRegex(
            ValueError,
            "SIGNING_MANIFEST_MISMATCH",
        ):
            service.broadcast(
                "secret",
                review,
            )

        self.assertEqual(
            len(signer.calls),
            1,
        )

        self.assertEqual(
            wallet.wallet.mark_signed_calls,
            ["draft-token"],
        )

        self.assertEqual(
            wallet.wallet.release_calls,
            [],
        )

        self.assertEqual(
            wallet.broadcast_calls,
            [],
        )

    def test_review_metadata_cannot_disagree_with_manifest(self):
        ring = FakeRing()
        wallet = FakeWallet()
        signer = FakeSignerService()

        service = PaymentService(
            FakeWalletService(
                ring,
                wallet,
            ),
            FakeNodeService(),
            signer_service=signer,
        )

        review = make_review(
            fee_atoms=311,
        )

        with self.assertRaisesRegex(
            ValueError,
            "SIGNING_REVIEW_MISMATCH",
        ):
            service.broadcast(
                "secret",
                review,
            )

        self.assertEqual(
            signer.calls,
            [],
        )

    def test_default_signer_boundary_is_installed(self):
        ring = FakeRing()
        wallet = FakeWallet()

        service = PaymentService(
            FakeWalletService(
                ring,
                wallet,
            ),
            FakeNodeService(),
        )

        self.assertEqual(
            service.signer.capabilities.backend_id,
            "local_wsp",
        )

    def test_legacy_direct_signing_path_is_disabled(self):
        service = WalletService()

        with self.assertRaisesRegex(
            RuntimeError,
            "LEGACY_SIGNING_PATH_DISABLED",
        ):
            service.send_payment(
                b"secret",
                object(),
                "wamrtsp1example",
                "1.0",
                1000,
            )


if __name__ == "__main__":
    unittest.main()
