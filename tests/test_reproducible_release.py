from pathlib import Path
import os
import tempfile
import unittest

from scripts.reproducible_release import (
    app_manifest,
    canonical_json,
    compare_manifests,
    manifest_digest,
)


class ReproducibleReleaseTests(
    unittest.TestCase
):
    def _tree(
        self,
        root: Path,
    ):
        (
            root
            / "Contents"
            / "MacOS"
        ).mkdir(
            parents=True
        )

        app = (
            root
            / "Contents"
            / "MacOS"
            / "wallet"
        )

        app.write_bytes(
            b"wallet-binary"
        )

        app.chmod(
            0o755
        )

    def test_identical_tree_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            a = root / "A"
            b = root / "B"

            self._tree(a)
            self._tree(b)

            ma = app_manifest(a)
            mb = app_manifest(b)

            self.assertEqual(
                compare_manifests(
                    ma,
                    mb,
                ),
                [],
            )

    def test_changed_bytes_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            a = root / "A"
            b = root / "B"

            self._tree(a)
            self._tree(b)

            (
                b
                / "Contents"
                / "MacOS"
                / "wallet"
            ).write_bytes(
                b"different"
            )

            self.assertTrue(
                compare_manifests(
                    app_manifest(a),
                    app_manifest(b),
                )
            )

    def test_changed_mode_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            a = root / "A"
            b = root / "B"

            self._tree(a)
            self._tree(b)

            (
                b
                / "Contents"
                / "MacOS"
                / "wallet"
            ).chmod(
                0o644
            )

            self.assertTrue(
                compare_manifests(
                    app_manifest(a),
                    app_manifest(b),
                )
            )

    def test_missing_file_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            a = root / "A"
            b = root / "B"

            self._tree(a)
            self._tree(b)

            (
                b
                / "Contents"
                / "MacOS"
                / "wallet"
            ).unlink()

            self.assertTrue(
                compare_manifests(
                    app_manifest(a),
                    app_manifest(b),
                )
            )

    def test_manifest_digest_stable(self):
        value = {
            "b": {
                "type": "file",
                "sha256": "b",
            },
            "a": {
                "type": "file",
                "sha256": "a",
            },
        }

        self.assertEqual(
            manifest_digest(
                value
            ),
            manifest_digest(
                dict(
                    reversed(
                        list(
                            value.items()
                        )
                    )
                )
            ),
        )

    def test_canonical_json_stable(self):
        self.assertEqual(
            canonical_json(
                {
                    "b": 2,
                    "a": 1,
                }
            ),
            canonical_json(
                {
                    "a": 1,
                    "b": 2,
                }
            ),
        )


if __name__ == "__main__":
    unittest.main()
