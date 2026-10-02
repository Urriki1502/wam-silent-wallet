"""Two-phase payment review/sign/broadcast orchestration."""

from dataclasses import dataclass

from wam_sp.wallet import Intent

from .fee_service import FeePolicyService
from .payment_journal import PaymentJournalService
from .signer_service import SignerService
from .transaction_manifest import SigningManifest


ATOMS_PER_WAM = 100_000_000


@dataclass(frozen=True)
class PaymentReview:
    proposal: object
    manifest: SigningManifest
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
        signer_service=None,
        journal_service=None,
    ):
        self.wallet_service = wallet_service
        self.node_service = node_service
        self.signer = (
            signer_service
            if signer_service is not None
            else SignerService()
        )
        self.fees = FeePolicyService(
            node_service
        )

        if journal_service is not None:
            self.journal = journal_service

        elif hasattr(
            wallet_service,
            "payment_journal",
        ):
            self.journal = (
                wallet_service
                .payment_journal
            )

        elif hasattr(
            wallet_service,
            "data_dir",
        ):
            self.journal = (
                PaymentJournalService(
                    wallet_service.data_dir
                )
            )

        else:
            self.journal = None

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

    @staticmethod
    def _assert_review_integrity(
        review: PaymentReview,
    ) -> None:
        if not isinstance(
            review,
            PaymentReview,
        ):
            raise ValueError(
                "PAYMENT_REVIEW_REQUIRED"
            )

        manifest = review.manifest

        if not isinstance(
            manifest,
            SigningManifest,
        ):
            raise ValueError(
                "SIGNING_MANIFEST_REQUIRED"
            )

        manifest.assert_matches(
            review.proposal
        )

        # The current desktop send flow is intentionally
        # single-recipient.  Any future multi-recipient UI
        # must introduce a new review representation rather
        # than silently weakening this invariant.
        if len(manifest.intents) != 1:
            raise ValueError(
                "SIGNING_REVIEW_MISMATCH"
            )

        intent = manifest.intents[0]

        selected_atoms = sum(
            item.atoms
            for item in manifest.inputs
        )

        change_atoms = (
            selected_atoms
            - intent.atoms
            - manifest.fee
        )

        if change_atoms < 0:
            raise ValueError(
                "SIGNING_REVIEW_MISMATCH"
            )

        output_count = (
            1
            if change_atoms == 0
            else 2
        )

        if (
            review.destination
            != intent.code
            or review.amount_atoms
            != intent.atoms
            or review.fee_atoms
            != manifest.fee
            or review.input_count
            != len(manifest.inputs)
            or review.change_atoms
            != change_atoms
            or review.output_count
            != output_count
        ):
            raise ValueError(
                "SIGNING_REVIEW_MISMATCH"
            )

    def review(
        self,
        passphrase: str,
        destination: str,
        amount_text: str,
        tier: str,
    ) -> PaymentReview:
        self.wallet_service.assert_spend_ready()

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
                        manifest=(
                            SigningManifest
                            .from_proposal(
                                proposal
                            )
                        ),
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
        self.wallet_service.assert_spend_ready()

        # Validate the user-approved transaction commitment
        # before private key material is opened.
        self._assert_review_integrity(
            review
        )

        approved_intents = tuple(
            Intent(
                item.code,
                item.atoms,
            )
            for item in review.manifest.intents
        )

        ring, wallet = (
            self.wallet_service
            ._open(passphrase)
        )

        try:
            # Scanner readiness belongs to a wallet instance.
            # Re-scan after reopening so broadcast never relies
            # on stale in-memory state.
            wallet.scan(
                self.node_service
                .scanner_chain(),
                mempool=True,
            )

            # Re-check immediately before invoking the signer.
            # A mutable nested proposal dictionary must never
            # cross the signing boundary unnoticed.
            self._assert_review_integrity(
                review
            )

            signed_psbt = (
                self.signer
                .sign(
                    keyring=ring,
                    proposal=review.proposal,
                    approval_manifest=(
                        review.manifest
                    ),
                    approved_intents=(
                        approved_intents
                    ),
                    approved_max_fee=(
                        review.manifest.fee
                    ),
                )
            )

            # Persist signed transaction material before the
            # reservation crosses the irreversible signed boundary.
            # If this write fails, the reservation is still a draft
            # and the outer failure path may safely release it.
            if self.journal is not None:
                self.journal.record_signed(
                    review.manifest
                    .reservation_token,
                    review.manifest.digest,
                    signed_psbt,
                )

            # Once signature material exists, the input
            # reservation is no longer a disposable draft.
            # Subsequent failures must not automatically make
            # these coins available for another transaction.
            wallet.wallet.mark_signed(
                review.manifest
                .reservation_token
            )

            if self.journal is not None:
                self.journal.transition(
                    review.manifest
                    .reservation_token,
                    "signed",
                )

            # A signer backend must not mutate the coordinator
            # proposal while signing.  PSBT byte-level output
            # verification is handled by the next boundary.
            self._assert_review_integrity(
                review
            )

            # Signature material already exists here.
            # A transport/node failure during broadcast has an
            # ambiguous outcome: the node may have accepted the
            # transaction before the response was lost.
            #
            # Never expose this as an ordinary retryable failure.
            if self.journal is not None:
                self.journal.transition(
                    review.manifest
                    .reservation_token,
                    "broadcasting",
                )

            try:
                txid = wallet.broadcast(
                    signed_psbt,
                    review.manifest
                    .reservation_token,
                    self.node_service
                    .broadcast_chain(),
                )


            except Exception as exc:
                if self.journal is not None:
                    try:
                        self.journal.transition(
                            review.manifest
                            .reservation_token,
                            "uncertain",
                        )
                    except Exception:
                        pass

                raise RuntimeError(
                    "BROADCAST_OUTCOME_UNCERTAIN"
                ) from exc

            if self.journal is not None:
                try:
                    self.journal.transition(
                        review.manifest
                        .reservation_token,
                        "broadcast",
                        txid=txid,
                    )
                except Exception:
                    # Broadcast already succeeded.  Never turn a
                    # known-successful payment into an apparent send
                    # failure because the local journal update failed.
                    pass

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
                "signing_manifest": (
                    review.manifest.digest
                ),
            }

        except Exception:
            # This releases only reservations that are still
            # drafts. mark_signed() deliberately makes this a
            # no-op after signature material has been created.
            self._release_draft(
                wallet,
                review.proposal,
            )

            raise

        finally:
            wallet.close()
            ring.close()
