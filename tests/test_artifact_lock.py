from pathlib import Path
import tempfile
import unittest

from scripts.artifact_lock import (
    build_sbom,
    canonical_name,
    json_bytes,
    requirement_text,
    safe_filename,
    sha256_file,
    verify,
)


class ArtifactLockTests(
    unittest.TestCase
):
    def test_canonical_name(self):
        self.assertEqual(
            canonical_name(
                "PySide6_Addons"
            ),
            "pyside6-addons",
        )

    def test_safe_filename(self):
        self.assertEqual(
            safe_filename(
                "package.whl"
            ),
            "package.whl",
        )

    def test_path_escape_rejected(self):
        with self.assertRaisesRegex(
            RuntimeError,
            "UNSAFE_ARTIFACT_FILENAME",
        ):
            safe_filename(
                "../package.whl"
            )

    def test_requirement_contains_hash(self):
        text = requirement_text(
            [
                {
                    "name": "Example",
                    "version": "1.2.3",
                    "sha256": "a" * 64,
                }
            ]
        )

        self.assertIn(
            "Example==1.2.3",
            text,
        )

        self.assertIn(
            "--hash=sha256:",
            text,
        )

    def test_json_bytes_deterministic(self):
        self.assertEqual(
            json_bytes(
                {
                    "b": 2,
                    "a": 1,
                }
            ),
            json_bytes(
                {
                    "a": 1,
                    "b": 2,
                }
            ),
        )

    def test_sbom_deterministic(self):
        lock = {
            "wam_silent_payments": {
                "version": "1.0.0",
                "commit": "a" * 40,
                "sha256": "b" * 64,
            },
            "wheels": [
                {
                    "name": "Example",
                    "version": "1.0",
                    "sha256": "c" * 64,
                }
            ],
        }

        self.assertEqual(
            build_sbom(lock),
            build_sbom(lock),
        )

    def test_verify_detects_wheel_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            (
                root
                / "vendor"
                / "wheelhouse"
            ).mkdir(
                parents=True
            )

            (
                root
                / "supply-chain.lock.json"
            ).write_text(
                "{}\n"
            )

            wheel = (
                root
                / "vendor"
                / "wheelhouse"
                / "example.whl"
            )

            wheel.write_bytes(
                b"tampered"
            )

            archive = (
                root
                / "vendor"
                / "wsp.tar"
            )

            archive.write_bytes(
                b"source"
            )

            lock = {
                "supply_chain_lock_sha256": (
                    sha256_file(
                        root
                        / "supply-chain.lock.json"
                    )
                ),
                "wheels": [
                    {
                        "filename": "example.whl",
                        "size": 8,
                        "sha256": "0" * 64,
                    }
                ],
                "wam_silent_payments": {
                    "filename": "wsp.tar",
                    "size": 6,
                    "sha256": (
                        sha256_file(
                            archive
                        )
                    ),
                },
            }

            failures = verify(
                root,
                lock,
            )

            self.assertTrue(
                any(
                    "wheel hash mismatch"
                    in item
                    for item in failures
                )
            )

    def test_verify_clean_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            (
                root
                / "vendor"
                / "wheelhouse"
            ).mkdir(
                parents=True
            )

            supply = (
                root
                / "supply-chain.lock.json"
            )

            supply.write_text(
                "{}\n"
            )

            wheel = (
                root
                / "vendor"
                / "wheelhouse"
                / "example.whl"
            )

            wheel.write_bytes(
                b"wheel"
            )

            archive = (
                root
                / "vendor"
                / "wsp.tar"
            )

            archive.write_bytes(
                b"source"
            )

            lock = {
                "supply_chain_lock_sha256": (
                    sha256_file(
                        supply
                    )
                ),
                "wheels": [
                    {
                        "filename": "example.whl",
                        "size": 5,
                        "sha256": (
                            sha256_file(
                                wheel
                            )
                        ),
                    }
                ],
                "wam_silent_payments": {
                    "filename": "wsp.tar",
                    "size": 6,
                    "sha256": (
                        sha256_file(
                            archive
                        )
                    ),
                },
            }

            self.assertEqual(
                verify(
                    root,
                    lock,
                ),
                [],
            )


if __name__ == "__main__":
    unittest.main()
