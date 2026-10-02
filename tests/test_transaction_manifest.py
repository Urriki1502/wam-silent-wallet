import dataclasses
import unittest

from wam_sp.wallet import (
    Intent,
    Proposal,
)

from wam_silent_wallet.services.transaction_manifest import (
    SigningManifest,
)


def proposal():
    coin = {
        "txid": "11" * 32,
        "vout": 1,
        "account": "account-1",
        "epoch": 0,
        "atoms": 2_000_000,
        "public_key": "22" * 32,
        "tweak": "33" * 32,
        "label": 0,
        "k": 7,
    }

    return Proposal(
        coins=(coin,),
        intents=(
            Intent(
                "wamrtsp1example",
                1_000_000,
            ),
        ),
        fee=500,
        change_epoch=0,
        token="reservation-token",
    )


class SigningManifestTests(
    unittest.TestCase
):
    def test_manifest_is_deterministic(self):
        first = SigningManifest.from_proposal(
            proposal()
        )

        second = SigningManifest.from_proposal(
            proposal()
        )

        self.assertEqual(
            first,
            second,
        )

        self.assertEqual(
            len(first.digest),
            64,
        )

    def test_manifest_is_frozen(self):
        manifest = SigningManifest.from_proposal(
            proposal()
        )

        with self.assertRaises(
            dataclasses.FrozenInstanceError
        ):
            manifest.fee = 999

    def test_mutated_coin_is_rejected(self):
        item = proposal()

        manifest = SigningManifest.from_proposal(
            item
        )

        item.coins[0]["atoms"] += 1

        with self.assertRaisesRegex(
            ValueError,
            "SIGNING_MANIFEST_MISMATCH",
        ):
            manifest.assert_matches(
                item
            )

    def test_mutated_fee_is_rejected(self):
        item = proposal()

        manifest = SigningManifest.from_proposal(
            item
        )

        changed = Proposal(
            coins=item.coins,
            intents=item.intents,
            fee=item.fee + 1,
            change_epoch=item.change_epoch,
            token=item.token,
        )

        with self.assertRaisesRegex(
            ValueError,
            "SIGNING_MANIFEST_MISMATCH",
        ):
            manifest.assert_matches(
                changed
            )

    def test_mutated_intent_is_rejected(self):
        item = proposal()

        manifest = SigningManifest.from_proposal(
            item
        )

        changed = Proposal(
            coins=item.coins,
            intents=(
                Intent(
                    item.intents[0].code,
                    item.intents[0].atoms + 1,
                ),
            ),
            fee=item.fee,
            change_epoch=item.change_epoch,
            token=item.token,
        )

        with self.assertRaisesRegex(
            ValueError,
            "SIGNING_MANIFEST_MISMATCH",
        ):
            manifest.assert_matches(
                changed
            )

    def test_changed_reservation_is_rejected(self):
        item = proposal()

        manifest = SigningManifest.from_proposal(
            item
        )

        changed = Proposal(
            coins=item.coins,
            intents=item.intents,
            fee=item.fee,
            change_epoch=item.change_epoch,
            token="different-token",
        )

        with self.assertRaisesRegex(
            ValueError,
            "SIGNING_MANIFEST_MISMATCH",
        ):
            manifest.assert_matches(
                changed
            )


if __name__ == "__main__":
    unittest.main()
