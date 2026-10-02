import json
import os
from pathlib import Path
import tempfile
import unittest

from wam_silent_wallet.services.payment_journal import (
    PaymentJournalService,
)


TOKEN = "draft-token"
MANIFEST = "11" * 32
PSBT = b"signed-psbt-fixture"


class PaymentJournalTests(
    unittest.TestCase
):
    def make_service(self):
        tmp = tempfile.TemporaryDirectory()

        root = Path(
            tmp.name
        )

        os.chmod(
            root,
            0o700,
        )

        return (
            tmp,
            PaymentJournalService(
                root
            ),
        )

    def test_signed_material_survives_reload(self):
        tmp, journal = self.make_service()

        try:
            journal.record_signed(
                TOKEN,
                MANIFEST,
                PSBT,
            )

            loaded = journal.load(
                TOKEN
            )

            self.assertEqual(
                loaded["state"],
                "signed_material",
            )

            self.assertEqual(
                loaded[
                    "manifest_digest"
                ],
                MANIFEST,
            )

            self.assertEqual(
                loaded[
                    "signed_psbt"
                ],
                PSBT,
            )

        finally:
            tmp.cleanup()

    def test_state_machine_reaches_broadcast(self):
        tmp, journal = self.make_service()

        try:
            journal.record_signed(
                TOKEN,
                MANIFEST,
                PSBT,
            )

            journal.transition(
                TOKEN,
                "signed",
            )

            journal.transition(
                TOKEN,
                "broadcasting",
            )

            journal.transition(
                TOKEN,
                "broadcast",
                txid="22" * 32,
            )

            loaded = journal.load(
                TOKEN
            )

            self.assertEqual(
                loaded["state"],
                "broadcast",
            )

            self.assertEqual(
                loaded["txid"],
                "22" * 32,
            )

        finally:
            tmp.cleanup()

    def test_uncertain_state_is_persistent(self):
        tmp, journal = self.make_service()

        try:
            journal.record_signed(
                TOKEN,
                MANIFEST,
                PSBT,
            )

            journal.transition(
                TOKEN,
                "signed",
            )

            journal.transition(
                TOKEN,
                "broadcasting",
            )

            journal.transition(
                TOKEN,
                "uncertain",
            )

            reloaded = (
                PaymentJournalService(
                    journal.data_dir
                )
            )

            loaded = reloaded.load(
                TOKEN
            )

            self.assertEqual(
                loaded["state"],
                "uncertain",
            )

        finally:
            tmp.cleanup()

    def test_corrupted_signed_material_is_rejected(self):
        tmp, journal = self.make_service()

        try:
            journal.record_signed(
                TOKEN,
                MANIFEST,
                PSBT,
            )

            path = journal._path(
                TOKEN
            )

            payload = json.loads(
                path.read_text()
            )

            payload[
                "psbt_hex"
            ] = b"tampered".hex()

            path.write_text(
                json.dumps(
                    payload
                )
            )

            os.chmod(
                path,
                0o600,
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "PAYMENT_JOURNAL_CORRUPT_OR_UNSAFE",
            ):
                journal.load(
                    TOKEN
                )

        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
