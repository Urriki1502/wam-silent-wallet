import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts.supply_chain import (
    canonical_json_bytes,
    canonical_name,
    manifest_diff,
    sha256_bytes,
    source_identity,
    validate_exact_pins,
)


class SupplyChainTests(
    unittest.TestCase
):
    def test_canonical_name(self):
        self.assertEqual(
            canonical_name(
                "PySide6_Essentials"
            ),
            "pyside6-essentials",
        )

    def test_canonical_json_is_stable(self):
        a = {
            "b": 2,
            "a": 1,
        }

        b = {
            "a": 1,
            "b": 2,
        }

        self.assertEqual(
            canonical_json_bytes(
                a
            ),
            canonical_json_bytes(
                b
            ),
        )

        self.assertEqual(
            sha256_bytes(
                canonical_json_bytes(
                    a
                )
            ),
            sha256_bytes(
                canonical_json_bytes(
                    b
                )
            ),
        )

    def test_exact_pins_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = (
                Path(tmp)
                / "pyproject.toml"
            )

            path.write_text(
                """
[build-system]
requires = [
    "setuptools==84.0.0",
    "wheel==0.46.3"
]

[project]
name = "example"
version = "1.0.0"
dependencies = [
    "PySide6==6.11.0"
]
""".strip()
                + "\n"
            )

            validate_exact_pins(
                path
            )

    def test_ranged_dependency_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = (
                Path(tmp)
                / "pyproject.toml"
            )

            path.write_text(
                """
[build-system]
requires = [
    "setuptools>=69"
]

[project]
name = "example"
version = "1.0.0"
dependencies = [
    "PySide6>=6.11,<7"
]
""".strip()
                + "\n"
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "UNPINNED_DEPENDENCY",
            ):
                validate_exact_pins(
                    path
                )

    def test_manifest_diff_equal(self):
        value = {
            "a": [
                {
                    "b": 1,
                }
            ]
        }

        self.assertEqual(
            manifest_diff(
                value,
                json.loads(
                    json.dumps(
                        value
                    )
                ),
            ),
            [],
        )

    def test_manifest_diff_detects_change(self):
        differences = manifest_diff(
            {
                "version": "1",
            },
            {
                "version": "2",
            },
        )

        self.assertTrue(
            differences
        )

    def test_source_identity_requires_clean_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            subprocess.run(
                [
                    "git",
                    "init",
                    "-q",
                    str(root),
                ],
                check=True,
            )

            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "config",
                    "user.email",
                    "test@example.invalid",
                ],
                check=True,
            )

            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "config",
                    "user.name",
                    "Test",
                ],
                check=True,
            )

            (
                root
                / "pyproject.toml"
            ).write_text(
                """
[project]
name = "fixture"
version = "1.2.3"
""".strip()
                + "\n"
            )

            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "add",
                    "pyproject.toml",
                ],
                check=True,
            )

            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "commit",
                    "-qm",
                    "fixture",
                ],
                check=True,
            )

            identity = source_identity(
                root
            )

            self.assertEqual(
                identity["version"],
                "1.2.3",
            )

            self.assertEqual(
                len(
                    identity["commit"]
                ),
                40,
            )

            (
                root
                / "dirty.txt"
            ).write_text(
                "dirty\n"
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "SOURCE_REPOSITORY_DIRTY",
            ):
                source_identity(
                    root
                )


if __name__ == "__main__":
    unittest.main()
