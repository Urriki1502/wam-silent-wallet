import unittest
from decimal import Decimal

from wam_silent_wallet.services.fee_service import FeePolicyService


class FeePolicyTests(unittest.TestCase):
    def test_rate_conversion(self):
        self.assertEqual(
            FeePolicyService._rate_from_wam_kvb(
                Decimal("0.00001000")
            ),
            1,
        )

        self.assertEqual(
            FeePolicyService._rate_from_wam_kvb(
                Decimal("0.00002000")
            ),
            2,
        )

    def test_conservative_p2tr_vsize(self):
        self.assertEqual(
            FeePolicyService.estimate_vsize(
                1,
                2,
            ),
            155,
        )

        self.assertEqual(
            FeePolicyService.estimate_vsize(
                2,
                2,
            ),
            213,
        )

    def test_fee_math(self):
        fee, vsize = (
            FeePolicyService.fee_for(
                2,
                1,
                2,
            )
        )

        self.assertEqual(
            vsize,
            155,
        )

        self.assertEqual(
            fee,
            310,
        )


if __name__ == "__main__":
    unittest.main()
