"""Signer boundary for WAM Silent Wallet.

The coordinator freezes an approved proposal into a canonical unsigned PSBT.
The signing backend receives that frozen PSBT and may add signatures only.

No passphrase, keyring, proposal or PSBT is retained after a signing call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from wam_sp.wallet import (
    Prepared,
    Signer,
)

from .psbt_boundary import (
    PsbtBoundary,
)
from .transaction_manifest import (
    SigningManifest,
)


@dataclass(frozen=True)
class SignerCapabilities:
    backend_id: str
    local_private_keys: bool
    hardware_signing: bool
    secure_enclave: bool


class SignerPreparer(Protocol):
    def prepare(
        self,
        *,
        keyring,
        proposal,
    ) -> bytes:
        ...


class SignerBackend(Protocol):
    @property
    def capabilities(
        self,
    ) -> SignerCapabilities:
        ...

    def sign(
        self,
        *,
        keyring,
        proposal,
        prepared_psbt: bytes,
        approved_intents,
        approved_max_fee: int,
    ) -> bytes:
        ...


class LocalWspPreparer:
    """Construct the frozen unsigned WSP PSBT."""

    def prepare(
        self,
        *,
        keyring,
        proposal,
    ) -> bytes:
        signer = Signer(
            keyring
        )

        prepared = signer.prepare(
            proposal
        )

        return bytes(
            prepared.psbt
        )


class LocalWspSignerBackend:
    """Current in-process WSP signature backend."""

    @property
    def capabilities(
        self,
    ) -> SignerCapabilities:
        return SignerCapabilities(
            backend_id="local_wsp",
            local_private_keys=True,
            hardware_signing=False,
            secure_enclave=False,
        )

    def sign(
        self,
        *,
        keyring,
        proposal,
        prepared_psbt: bytes,
        approved_intents,
        approved_max_fee: int,
    ) -> bytes:
        signer = Signer(
            keyring
        )

        prepared = Prepared(
            proposal,
            prepared_psbt,
        )

        return signer.sign(
            prepared,
            approved_intents,
            approved_max_fee,
        )


class SignerService:
    """Stable transaction signing security boundary."""

    def __init__(
        self,
        backend: SignerBackend | None = None,
        preparer: SignerPreparer | None = None,
    ):
        self.backend = (
            backend
            if backend is not None
            else LocalWspSignerBackend()
        )

        self.preparer = (
            preparer
            if preparer is not None
            else LocalWspPreparer()
        )

    @property
    def capabilities(
        self,
    ) -> SignerCapabilities:
        return self.backend.capabilities

    def sign(
        self,
        *,
        keyring,
        proposal,
        approval_manifest,
        approved_intents,
        approved_max_fee: int,
    ) -> bytes:
        if keyring is None:
            raise ValueError(
                "SIGNER_KEYRING_REQUIRED"
            )

        if proposal is None:
            raise ValueError(
                "SIGNER_PROPOSAL_REQUIRED"
            )

        if not isinstance(
            approval_manifest,
            SigningManifest,
        ):
            raise ValueError(
                "SIGNER_MANIFEST_REQUIRED"
            )

        if (
            type(approved_max_fee)
            is not int
            or approved_max_fee <= 0
        ):
            raise ValueError(
                "SIGNER_FEE_APPROVAL"
            )

        # Proposal must still equal what the user approved.
        approval_manifest.assert_matches(
            proposal
        )

        prepared_psbt = (
            self.preparer
            .prepare(
                keyring=keyring,
                proposal=proposal,
            )
        )

        boundary = (
            PsbtBoundary
            .from_prepared(
                prepared_psbt,
                approval_manifest,
            )
        )

        signed = self.backend.sign(
            keyring=keyring,
            proposal=proposal,
            prepared_psbt=prepared_psbt,
            approved_intents=(
                approved_intents
            ),
            approved_max_fee=(
                approved_max_fee
            ),
        )

        if (
            not isinstance(
                signed,
                (bytes, bytearray),
            )
            or len(signed) == 0
        ):
            raise ValueError(
                "SIGNER_RESULT"
            )

        signed = bytes(
            signed
        )

        # Backend is allowed to add signatures.
        # Nothing else may change.
        boundary.assert_signed(
            signed
        )

        # Detect mutable proposal corruption during backend call.
        approval_manifest.assert_matches(
            proposal
        )

        return signed
