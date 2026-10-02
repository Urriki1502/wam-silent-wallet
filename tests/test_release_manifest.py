from pathlib import Path
import json
import tempfile
import unittest

from scripts.release_manifest import (
    file_record,
    sha256_file,
    verify_manifest,
)


class ReleaseManifestTests(
    unittest.TestCase
):
    def test_sha256_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.bin"
            path.write_bytes(b"abc")

            self.assertEqual(
                sha256_file(path),
                (
                    "ba7816bf8f01cfea414140de5dae2223"
                    "b00361a396177a9cb410ff61f20015ad"
                ),
            )

    def test_file_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "artifact.bin"
            path.write_bytes(b"payload")

            record = file_record(
                path,
                root,
            )

            self.assertEqual(
                record["path"],
                "artifact.bin",
            )
            self.assertEqual(
                record["size"],
                7,
            )

    def test_missing_artifact_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with self.assertRaisesRegex(
                RuntimeError,
                "RELEASE_ARTIFACT_MISSING",
            ):
                file_record(
                    root / "missing",
                    root,
                )

    def test_verify_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "artifact.bin"
            artifact.write_bytes(b"payload")

            record = file_record(
                artifact,
                root,
            )

            manifest = {
                "release_inputs": {},
                "artifacts": [record],
            }

            self.assertEqual(
                verify_manifest(
                    root,
                    manifest,
                ),
                [],
            )

    def test_verify_detects_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "artifact.bin"
            artifact.write_bytes(b"payload")

            record = file_record(
                artifact,
                root,
            )

            artifact.write_bytes(
                b"tampered"
            )

            manifest = {
                "release_inputs": {},
                "artifacts": [record],
            }

            failures = verify_manifest(
                root,
                manifest,
            )

            self.assertTrue(
                any(
                    item.startswith(
                        "sha256:"
                    )
                    for item in failures
                )
            )

    def test_manifest_is_json_serializable(self):
        value = {
            "schema": 1,
            "signing": {
                "mode": "adhoc",
                "notarized": False,
            },
        }

        encoded = json.dumps(
            value,
            sort_keys=True,
        )

        self.assertIn(
            '"schema": 1',
            encoded,
        )


if __name__ == "__main__":
    unittest.main()
