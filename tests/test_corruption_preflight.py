import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from wam_silent_wallet.services.wallet_service import (
    WalletService,
)


MAGIC = b"WAMSP02\x00"


def write_keys(
    root: Path,
    payload: bytes | None = None,
):
    path = root / "keys.wsp"

    if payload is None:
        payload = (
            MAGIC
            + b"\x00" * 44
        )

    path.write_bytes(
        payload
    )

    os.chmod(
        path,
        0o600,
    )


def write_sqlite(
    root: Path,
):
    path = root / "wallet.db"

    db = sqlite3.connect(
        path
    )

    try:
        db.execute(
            "CREATE TABLE probe(x INTEGER)"
        )
        db.commit()

    finally:
        db.close()

    os.chmod(
        path,
        0o600,
    )


class CorruptionPreflightTests(
    unittest.TestCase
):
    def test_valid_outer_fileset_passes_preflight(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)

            write_sqlite(root)
            write_keys(root)

            service = WalletService(
                root
            )

            service._validate_keys_preflight()
            service._validate_database_preflight()

            self.assertTrue(
                service.exists()
            )

    def test_zero_length_database_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)

            path = root / "wallet.db"

            path.write_bytes(
                b""
            )

            os.chmod(
                path,
                0o600,
            )

            write_keys(root)

            service = WalletService(
                root
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "WALLET_DATABASE_CORRUPT",
            ):
                service._validate_database_preflight()

    def test_invalid_database_header_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)

            path = root / "wallet.db"

            path.write_bytes(
                b"X" * 4096
            )

            os.chmod(
                path,
                0o600,
            )

            write_keys(root)

            service = WalletService(
                root
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "WALLET_DATABASE_CORRUPT",
            ):
                service._validate_database_preflight()

    def test_damaged_sqlite_pages_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)

            write_sqlite(root)
            write_keys(root)

            path = root / "wallet.db"

            raw = bytearray(
                path.read_bytes()
            )

            raw[100:300] = (
                b"\xff" * 200
            )

            path.write_bytes(
                raw
            )

            os.chmod(
                path,
                0o600,
            )

            service = WalletService(
                root
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "WALLET_DATABASE_CORRUPT",
            ):
                service._validate_database_preflight()

    def test_truncated_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)

            write_sqlite(root)

            write_keys(
                root,
                b"WAM",
            )

            service = WalletService(
                root
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "WALLET_KEYS_CORRUPT",
            ):
                service._validate_keys_preflight()

    def test_wrong_keys_magic_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)

            write_sqlite(root)

            write_keys(
                root,
                b"BADMAGIC"
                + b"\x00" * 44,
            )

            service = WalletService(
                root
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "WALLET_KEYS_CORRUPT",
            ):
                service._validate_keys_preflight()

    def test_world_readable_keys_are_rejected(self):
        if os.name != "posix":
            self.skipTest(
                "POSIX permissions required"
            )

        with tempfile.TemporaryDirectory() as root:
            root = Path(root)

            write_sqlite(root)
            write_keys(root)

            os.chmod(
                root / "keys.wsp",
                0o644,
            )

            service = WalletService(
                root
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "WALLET_KEYS_CORRUPT_OR_UNSAFE",
            ):
                service._validate_keys_preflight()


if __name__ == "__main__":
    unittest.main()
