"""Two-phase payment review/sign/broadcast orchestration."""

from dataclasses import dataclass

from wam_sp.wallet import Signer

from .fee_service import FeePolicyService


ATOMS_PER_WAM = 100_000_000


@dataclass(frozen=True)
class PaymentReview:
    proposal: object
    destination: str
    amount_atoms: int
    fee_atoms: int
    fee_rate_atoms_vb: int
    estimated_vsize: int
    input_count: int
    output_count: int
    change_atoms: int
    tier: str
    fee_source: str

    @property
    def amount_wam(self) -> float:
        return self.amount_atoms / ATOMS_PER_WAM

    @property
    def fee_wam(self) -> float:
        return self.fee_atoms / ATOMS_PER_WAM


class PaymentService:
    """
    Coordinate fee review and the existing WSP signing/broadcast pipeline.

    Phase 1:
      - synchronize wallet state;
      - query node fee policy;
      - select/reserve coins;
      - converge fee against the actual selected input count;
      - return a review object without signing.

    Phase 2:
      - re-synchronize;
      - recompute/verify signing intent through the WSP Signer;
      - policy-check and broadcast through WAM Core.

    A user cancellation releases only a draft reservation.
    Uncertain/broadcast reservations are deliberately never auto-released.
    """

    MAX_FEE_ITERATIONS = 8

    def __init__(
        self,
        wallet_service,
        node_service,
    ):
        self.wallet_service = wallet_service
        self.node_service = node_service
        self.fees = FeePolicyService(
            node_service
        )

    @staticmethod
    def _release_draft(
        wallet,
        proposal,
    ):
        if proposal is None:
            return

        try:
            wallet.wallet.release_draft(
                proposal.token
            )
        except Exception:
            pass

    def review(
        self,
        passphrase: str,
        destination: str,
        amount_text: str,
        tier: str,
    ) -> PaymentReview:
        if (
            not isinstance(destination, str)
            or not destination.strip()
        ):
            raise ValueError(
                "DESTINATION_REQUIRED"
            )

        destination = destination.strip()

        amount_atoms = (
            self.wallet_service
            .amount_to_atoms(amount_text)
        )

        fee_quote = self.fees.quote(
            tier
        )

        fee_rate = fee_quote[
            "atoms_per_vb"
        ]

        fee_atoms, _ = self.fees.fee_for(
            fee_rate,
            1,
            2,
        )

        ring, wallet = (
            self.wallet_service
            ._open(passphrase)
        )

        proposal = None

        try:
            wallet.scan(
                self.node_service
                .scanner_chain(),
                mempool=True,
            )

            balance = wallet.get_balance()

            visited = set()

            for _ in range(
                self.MAX_FEE_ITERATIONS
            ):
                required = (
                    amount_atoms
                    + fee_atoms
                )

                if (
                    balance["available_atoms"]
                    < required
                ):
                    raise ValueError(
                        "INSUFFICIENT_FUNDS"
                    )

                proposal = (
                    wallet.construct_payment(
                        [
                            (
                                destination,
                                amount_atoms,
                            )
                        ],
                        fee_atoms,
                    )
                )

                selected_atoms = sum(
                    coin["atoms"]
                    for coin in proposal.coins
                )

                change_atoms = (
                    selected_atoms
                    - amount_atoms
                    - fee_atoms
                )

                output_count = (
                    1
                    if change_atoms == 0
                    else 2
                )

                next_fee, vsize = (
                    self.fees.fee_for(
                        fee_rate,
                        len(proposal.coins),
                        output_count,
                    )
                )

                state = (
                    fee_atoms,
                    next_fee,
                    len(proposal.coins),
                    output_count,
                    tuple(
                        (
                            coin["txid"],
                            coin["vout"],
                        )
                        for coin in proposal.coins
                    ),
                )

                if next_fee == fee_atoms:
                    return PaymentReview(
                        proposal=proposal,
                        destination=destination,
                        amount_atoms=amount_atoms,
                        fee_atoms=fee_atoms,
                        fee_rate_atoms_vb=fee_rate,
                        estimated_vsize=vsize,
                        input_count=len(
                            proposal.coins
                        ),
                        output_count=output_count,
                        change_atoms=change_atoms,
                        tier=tier,
                        fee_source=fee_quote[
                            "source"
                        ],
                    )

                self._release_draft(
                    wallet,
                    proposal,
                )

                proposal = None

                if state in visited:
                    raise ValueError(
                        "FEE_CONVERGENCE"
                    )

                visited.add(state)

                fee_atoms = next_fee

            raise ValueError(
                "FEE_CONVERGENCE"
            )

        except Exception:
            self._release_draft(
                wallet,
                proposal,
            )

            raise

        finally:
            wallet.close()
            ring.close()

    def cancel(
        self,
        passphrase: str,
        review: PaymentReview,
    ):
        ring, wallet = (
            self.wallet_service
            ._open(passphrase)
        )

        try:
            wallet.wallet.release_draft(
                review.proposal.token
            )
        finally:
            wallet.close()
            ring.close()

    def broadcast(
        self,
        passphrase: str,
        review: PaymentReview,
    ) -> dict:
        ring, wallet = (
            self.wallet_service
            ._open(passphrase)
        )

        try:
            # Scanner readiness belongs to a wallet instance.  Re-scan after
            # reopening so broadcast never relies on stale in-memory state.
            wallet.scan(
                self.node_service
                .scanner_chain(),
                mempool=True,
            )

            signer = Signer(
                ring
            )

            prepared = signer.prepare(
                review.proposal
            )

            signed_psbt = signer.sign(
                prepared,
                review.proposal.intents,
                review.fee_atoms,
            )

            txid = wallet.broadcast(
                signed_psbt,
                review.proposal.token,
                self.node_service
                .broadcast_chain(),
            )

            return {
                "txid": txid,
                "amount_atoms": review.amount_atoms,
                "amount_wam": review.amount_wam,
                "fee_atoms": review.fee_atoms,
                "fee_wam": review.fee_wam,
                "fee_rate_atoms_vb": (
                    review.fee_rate_atoms_vb
                ),
                "estimated_vsize": (
                    review.estimated_vsize
                ),
                "inputs": review.input_count,
                "outputs": review.output_count,
                "change_atoms": review.change_atoms,
                "tier": review.tier,
                "fee_source": review.fee_source,
            }

        except Exception:
            self._release_draft(
                wallet,
                review.proposal,
            )

            raise

        finally:
            wallet.close()
            ring.close()
