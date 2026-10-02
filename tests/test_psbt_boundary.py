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

from wam_silent_wallet.services.psbt_boundary import (
    PsbtBoundary,
)
from wam_silent_wallet.services.transaction_manifest import (
    SigningManifest,
)


PUBKEY = (
    "79be667ef9dcbbac55a06295ce870b070"
    "29bfcdb2dce28d959f2815b16f81798"
)


def proposal():
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


def prepared_psbt():
    item = proposal()

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
                item.coins[0]["txid"],
                item.coins[0]["vout"],
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


def signed_from(
    raw,
):
    psbt = PSBT.decode(
        raw
    )

    return replace(
        psbt,
        signatures=(
            b"\x44" * 64,
        ),
    ).encode()


class PsbtBoundaryTests(
    unittest.TestCase
):
    def test_valid_prepared_and_signed_psbt_match(self):
        item = proposal()

        manifest = (
            SigningManifest
            .from_proposal(
                item
            )
        )

        prepared = prepared_psbt()

        boundary = (
            PsbtBoundary
            .from_prepared(
                prepared,
                manifest,
            )
        )

        boundary.assert_signed(
            signed_from(
                prepared
            )
        )

    def test_prepared_input_mutation_is_rejected(self):
        item = proposal()

        manifest = (
            SigningManifest
            .from_proposal(
                item
            )
        )

        psbt = PSBT.decode(
            prepared_psbt()
        )

        changed_tx = replace(
            psbt.tx,
            inputs=(
                (
                    "99" * 32,
                    1,
                ),
            ),
        )

        changed = replace(
            psbt,
            tx=changed_tx,
        ).encode()

        with self.assertRaisesRegex(
            ValueError,
            "PSBT_INPUT_MISMATCH",
        ):
            PsbtBoundary.from_prepared(
                changed,
                manifest,
            )

    def test_prepared_output_value_mutation_is_rejected(self):
        item = proposal()

        manifest = (
            SigningManifest
            .from_proposal(
                item
            )
        )

        psbt = PSBT.decode(
            prepared_psbt()
        )

        changed_tx = replace(
            psbt.tx,
            outputs=(
                (
                    999_999,
                    psbt.tx.outputs[0][1],
                ),
                psbt.tx.outputs[1],
            ),
        )

        changed = replace(
            psbt,
            tx=changed_tx,
        ).encode()

        with self.assertRaisesRegex(
            ValueError,
            "PSBT_OUTPUT_VALUE_MISMATCH",
        ):
            PsbtBoundary.from_prepared(
                changed,
                manifest,
            )

    def test_signed_output_script_mutation_is_rejected(self):
        item = proposal()

        manifest = (
            SigningManifest
            .from_proposal(
                item
            )
        )

        prepared = prepared_psbt()

        boundary = (
            PsbtBoundary
            .from_prepared(
                prepared,
                manifest,
            )
        )

        psbt = PSBT.decode(
            prepared
        )

        other_script = (
            b"\x51\x20"
            + bytes.fromhex(
                "c6047f9441ed7d6d3045406e95c07cd8"
                "5c778e4b8cef3ca7abac09b95c709ee5"
            )
        )

        changed_tx = replace(
            psbt.tx,
            outputs=(
                (
                    psbt.tx.outputs[0][0],
                    other_script,
                ),
                psbt.tx.outputs[1],
            ),
        )

        malicious = replace(
            psbt,
            tx=changed_tx,
            signatures=(
                b"\x44" * 64,
            ),
        ).encode()

        with self.assertRaisesRegex(
            ValueError,
            "PSBT_SIGNED_MISMATCH",
        ):
            boundary.assert_signed(
                malicious
            )

    def test_signed_fee_mutation_is_rejected(self):
        item = proposal()

        manifest = (
            SigningManifest
            .from_proposal(
                item
            )
        )

        prepared = prepared_psbt()

        boundary = (
            PsbtBoundary
            .from_prepared(
                prepared,
                manifest,
            )
        )

        psbt = PSBT.decode(
            prepared
        )

        changed_tx = replace(
            psbt.tx,
            outputs=(
                psbt.tx.outputs[0],
                (
                    psbt.tx.outputs[1][0]
                    - 1,
                    psbt.tx.outputs[1][1],
                ),
            ),
        )

        malicious = replace(
            psbt,
            tx=changed_tx,
            signatures=(
                b"\x44" * 64,
            ),
        ).encode()

        with self.assertRaisesRegex(
            ValueError,
            "PSBT_SIGNED_MISMATCH",
        ):
            boundary.assert_signed(
                malicious
            )

    def test_unsigned_backend_result_is_rejected(self):
        item = proposal()

        manifest = (
            SigningManifest
            .from_proposal(
                item
            )
        )

        prepared = prepared_psbt()

        boundary = (
            PsbtBoundary
            .from_prepared(
                prepared,
                manifest,
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "PSBT_SIGNATURE_REQUIRED",
        ):
            boundary.assert_signed(
                prepared
            )


if __name__ == "__main__":
    unittest.main()
