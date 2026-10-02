"""Signer boundary for WAM Silent Wallet.

The coordinator/wallet layer owns transaction construction and policy.  The
signer layer receives an already-approved proposal and is responsible only for
producing a signed WSP PSBT.

No passphrase, keyring or proposal is retained on SignerService after a call.
This makes the current local WSP signer replaceable by a future hardware or
OS-backed signer without changing payment orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from wam_sp.wallet import Signer


@dataclass(frozen=True)
class SignerCapabilities:
    backend_id: str
    local_private_keys: bool
    hardware_signing: bool
    secure_enclave: bool


class SignerBackend(Protocol):
    @property
    def capabilities(self) -> SignerCapabilities:
        ...

    def sign(
        self,
        *,
        keyring,
        proposal,
        approved_intents,
        approved_max_fee: int,
    ) -> bytes:
        ...


class LocalWspSignerBackend:
    """Current in-process WSP signer backend."""

    @property
    def capabilities(self) -> SignerCapabilities:
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
        approved_intents,
        approved_max_fee: int,
    ) -> bytes:
        signer = Signer(
            keyring
        )

        prepared = signer.prepare(
            proposal
        )

        return signer.sign(
            prepared,
            approved_intents,
            approved_max_fee,
        )


class SignerService:
    """Stable signing interface used by payment orchestration."""

    def __init__(
        self,
        backend: SignerBackend | None = None,
    ):
        self.backend = (
            backend
            if backend is not None
            else LocalWspSignerBackend()
        )

    @property
    def capabilities(self) -> SignerCapabilities:
        return self.backend.capabilities

    def sign(
        self,
        *,
        keyring,
        proposal,
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

        if (
            type(approved_max_fee) is not int
            or approved_max_fee <= 0
        ):
            raise ValueError(
                "SIGNER_FEE_APPROVAL"
            )

        signed = self.backend.sign(
            keyring=keyring,
            proposal=proposal,
            approved_intents=approved_intents,
            approved_max_fee=approved_max_fee,
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

        return bytes(
            signed
        )
