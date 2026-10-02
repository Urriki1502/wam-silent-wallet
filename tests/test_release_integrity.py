from pathlib import Path
import tempfile
import unittest

from scripts.release_integrity import (
    scan_release_tree,
    scan_tracked_paths,
)


class ReleaseIntegrityTests(
    unittest.TestCase
):
    def test_clean_release_tree_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            source = (
                root
                / "src"
                / "wam_silent_wallet"
            )

            source.mkdir(
                parents=True
            )

            (
                source
                / "safe.py"
            ).write_text(
                "VALUE = 1\n",
                encoding="utf-8",
            )

            self.assertEqual(
                scan_release_tree(
                    root
                ),
                [],
            )

    def test_tracked_wallet_database_is_rejected(self):
        findings = scan_tracked_paths(
            [
                Path(
                    "runtime/wallet.db"
                )
            ]
        )

        self.assertTrue(
            findings
        )

    def test_tracked_keys_file_is_rejected(self):
        findings = scan_tracked_paths(
            [
                Path(
                    "keys.wsp"
                )
            ]
        )

        self.assertTrue(
            findings
        )

    def test_tracked_recovery_bundle_is_rejected(self):
        findings = scan_tracked_paths(
            [
                Path(
                    "backup/wallet.wspbak"
                )
            ]
        )

        self.assertTrue(
            findings
        )

    def test_test_failpoint_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            source = (
                root
                / "src"
                / "wam_silent_wallet"
            )

            source.mkdir(
                parents=True
            )

            (
                source
                / "unsafe.py"
            ).write_text(
                'FLAG = "WAM_TEST_CRASH_AFTER_BROADCAST"\n',
                encoding="utf-8",
            )

            findings = scan_release_tree(
                root
            )

            self.assertTrue(
                any(
                    "test-only environment flag"
                    in item
                    for item in findings
                )
            )

    def test_absolute_developer_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            source = (
                root
                / "src"
                / "wam_silent_wallet"
            )

            source.mkdir(
                parents=True
            )

            (
                source
                / "unsafe.py"
            ).write_text(
                'PATH = "/Users/developer/wallet"\n',
                encoding="utf-8",
            )

            findings = scan_release_tree(
                root
            )

            self.assertTrue(
                any(
                    "developer home"
                    in item
                    for item in findings
                )
            )

    def test_private_key_pem_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            source = (
                root
                / "src"
                / "wam_silent_wallet"
            )

            source.mkdir(
                parents=True
            )

            (
                source
                / "unsafe.py"
            ).write_text(
                'KEY = """-----BEGIN PRIVATE KEY-----"""\n',
                encoding="utf-8",
            )

            findings = scan_release_tree(
                root
            )

            self.assertTrue(
                any(
                    "private-key PEM"
                    in item
                    for item in findings
                )
            )

    def test_release_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            source = (
                root
                / "src"
                / "wam_silent_wallet"
            )

            source.mkdir(
                parents=True
            )

            outside = (
                root
                / "outside.py"
            )

            outside.write_text(
                "VALUE = 1\n",
                encoding="utf-8",
            )

            (
                source
                / "linked.py"
            ).symlink_to(
                outside
            )

            findings = scan_release_tree(
                root
            )

            self.assertTrue(
                any(
                    "release symlink"
                    in item
                    for item in findings
                )
            )


if __name__ == "__main__":
    unittest.main()
