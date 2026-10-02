import unittest

from wam_silent_wallet.services.payment_service import (
    PaymentReview,
    PaymentService,
)


class FakeRing:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeWallet:
    def __init__(self):
        self.closed = False
        self.scan_calls = []
        self.broadcast_calls = []

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
    def __init__(self):
        self.calls = []

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

        return b"signed-psbt"


class Proposal:
    def __init__(self):
        self.token = "draft-token"
        self.intents = (
            object(),
        )


class PaymentSignerIntegrationTests(
    unittest.TestCase
):
    def test_broadcast_delegates_to_signer_boundary(self):
        ring = FakeRing()
        wallet = FakeWallet()
        wallet_service = FakeWalletService(
            ring,
            wallet,
        )
        node_service = FakeNodeService()
        signer_service = FakeSignerService()

        service = PaymentService(
            wallet_service,
            node_service,
            signer_service=signer_service,
        )

        proposal = Proposal()

        review = PaymentReview(
            proposal=proposal,
            destination="wamrtsp1example",
            amount_atoms=1_000_000,
            fee_atoms=310,
            fee_rate_atoms_vb=2,
            estimated_vsize=155,
            input_count=1,
            output_count=2,
            change_atoms=5_000_000,
            tier="Normal",
            fee_source="test",
        )

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
            proposal,
        )

        self.assertEqual(
            call["approved_intents"],
            proposal.intents,
        )

        self.assertEqual(
            call["approved_max_fee"],
            310,
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

        self.assertTrue(
            wallet.closed
        )

        self.assertTrue(
            ring.closed
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


if __name__ == "__main__":
    unittest.main()
