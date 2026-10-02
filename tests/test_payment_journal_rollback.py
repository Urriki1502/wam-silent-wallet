import os
from pathlib import Path
import tempfile
import unittest

from wam_silent_wallet.services.payment_journal import (
    PaymentJournalService,
)


class PaymentJournalRollbackTests(unittest.TestCase):
    def test_broadcasting_rolls_back_to_signed_explicitly(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            os.chmod(
                root,
                0o700,
            )

            service = PaymentJournalService(
                root
            )

            service.record_signed(
                "rollback-token",
                "11" * 32,
                b"signed-psbt",
            )
            service.transition(
                "rollback-token",
                "signed",
            )
            service.transition(
                "rollback-token",
                "broadcasting",
            )

            service.rollback_broadcasting(
                "rollback-token"
            )

            self.assertEqual(
                service.load(
                    "rollback-token"
                )["state"],
                "signed",
            )


if __name__ == "__main__":
    unittest.main()
