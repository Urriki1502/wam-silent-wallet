"""PSBT integrity boundary for WAM Silent Wallet.

The coordinator freezes one canonical unsigned WSP PSBT before a signing
backend receives it.  The backend may add signatures only.

Any mutation to inputs, UTXOs, outputs, fee, Silent Payment metadata or other
unsigned PSBT fields after approval fails closed before broadcast.
"""

from __future__ import annotations

from dataclasses import (
    dataclass,
    replace,
)
from hashlib import sha256
import hmac

from wam_sp.psbt import PSBT

from .transaction_manifest import (
    SigningManifest,
)


_DOMAIN = (
    b"WAM-SILENT-WALLET/"
    b"PSBT-BOUNDARY/V1\x00"
)


@dataclass(frozen=True)
class PsbtBoundary:
    manifest_digest: str
    unsigned_digest: str
    input_count: int
    output_count: int

    @staticmethod
    def _unsigned_bytes(
        psbt: PSBT,
    ) -> bytes:
        clean = replace(
            psbt,
            signatures=(
                (None,)
                * len(psbt.tx.inputs)
            ),
        )

        return clean.encode()

    @classmethod
    def _digest(
        cls,
        *,
        manifest_digest: str,
        psbt: PSBT,
    ) -> str:
        unsigned = cls._unsigned_bytes(
            psbt
        )

        return sha256(
            _DOMAIN
            + manifest_digest.encode(
                "ascii"
            )
            + b"\x00"
            + unsigned
        ).hexdigest()

    @classmethod
    def from_prepared(
        cls,
        prepared_psbt: bytes,
        manifest: SigningManifest,
    ) -> "PsbtBoundary":
        if not isinstance(
            manifest,
            SigningManifest,
        ):
            raise ValueError(
                "PSBT_MANIFEST_REQUIRED"
            )

        if (
            not isinstance(
                prepared_psbt,
                bytes,
            )
            or not prepared_psbt
        ):
            raise ValueError(
                "PSBT_PREPARED_REQUIRED"
            )

        psbt = PSBT.decode(
            prepared_psbt
        )

        if psbt.version != 2:
            raise ValueError(
                "PSBT_VERSION_POLICY"
            )

        if any(
            signature is not None
            for signature
            in psbt.signatures
        ):
            raise ValueError(
                "PSBT_PREPARED_SIGNED"
            )

        # BIP-370 TX_MODIFIABLE must be frozen.
        if (
            psbt.global_extra.get(
                b"\x06",
                b"\x00",
            )
            != b"\x00"
        ):
            raise ValueError(
                "PSBT_NOT_FROZEN"
            )

        expected_inputs = tuple(
            (
                item.txid,
                item.vout,
            )
            for item in manifest.inputs
        )

        if (
            psbt.tx.inputs
            != expected_inputs
        ):
            raise ValueError(
                "PSBT_INPUT_MISMATCH"
            )

        expected_utxos = tuple(
            (
                item.atoms,
                b"\x51\x20"
                + bytes.fromhex(
                    item.public_key
                ),
            )
            for item in manifest.inputs
        )

        if psbt.utxos != expected_utxos:
            raise ValueError(
                "PSBT_UTXO_MISMATCH"
            )

        selected_atoms = sum(
            item.atoms
            for item in manifest.inputs
        )

        recipient_atoms = tuple(
            item.atoms
            for item in manifest.intents
        )

        change_atoms = (
            selected_atoms
            - sum(recipient_atoms)
            - manifest.fee
        )

        if change_atoms < 0:
            raise ValueError(
                "PSBT_VALUE_MISMATCH"
            )

        expected_values = (
            recipient_atoms
            + (
                (change_atoms,)
                if change_atoms
                else ()
            )
        )

        actual_values = tuple(
            value
            for value, _
            in psbt.tx.outputs
        )

        if (
            actual_values
            != expected_values
        ):
            raise ValueError(
                "PSBT_OUTPUT_VALUE_MISMATCH"
            )

        # Current WSP-1 sender path produces only
        # Taproot key-path outputs.
        if any(
            len(script) != 34
            or script[:2]
            != b"\x51\x20"
            for _, script
            in psbt.tx.outputs
        ):
            raise ValueError(
                "PSBT_OUTPUT_SCRIPT_POLICY"
            )

        actual_fee = (
            sum(
                value
                for value, _
                in psbt.utxos
            )
            - sum(actual_values)
        )

        if actual_fee != manifest.fee:
            raise ValueError(
                "PSBT_FEE_MISMATCH"
            )

        digest = cls._digest(
            manifest_digest=(
                manifest.digest
            ),
            psbt=psbt,
        )

        return cls(
            manifest_digest=(
                manifest.digest
            ),
            unsigned_digest=digest,
            input_count=len(
                psbt.tx.inputs
            ),
            output_count=len(
                psbt.tx.outputs
            ),
        )

    def assert_signed(
        self,
        signed_psbt: bytes,
    ) -> None:
        if (
            not isinstance(
                signed_psbt,
                bytes,
            )
            or not signed_psbt
        ):
            raise ValueError(
                "PSBT_SIGNED_REQUIRED"
            )

        psbt = PSBT.decode(
            signed_psbt
        )

        if psbt.version != 2:
            raise ValueError(
                "PSBT_VERSION_POLICY"
            )

        if (
            len(psbt.tx.inputs)
            != self.input_count
            or len(psbt.tx.outputs)
            != self.output_count
        ):
            raise ValueError(
                "PSBT_SIGNED_MISMATCH"
            )

        if (
            len(psbt.signatures)
            != self.input_count
            or any(
                signature is None
                for signature
                in psbt.signatures
            )
        ):
            raise ValueError(
                "PSBT_SIGNATURE_REQUIRED"
            )

        current = self._digest(
            manifest_digest=(
                self.manifest_digest
            ),
            psbt=psbt,
        )

        if not hmac.compare_digest(
            self.unsigned_digest,
            current,
        ):
            raise ValueError(
                "PSBT_SIGNED_MISMATCH"
            )
