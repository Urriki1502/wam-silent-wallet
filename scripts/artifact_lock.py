#!/usr/bin/env python3
"""Hash-locked wheelhouse, WSP source archive and CycloneDX SBOM."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


SCHEMA_VERSION = 1


def canonical_name(value: str) -> str:
    return re.sub(
        r"[-_.]+",
        "-",
        value,
    ).lower()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(
                1024 * 1024
            )

            if not chunk:
                break

            h.update(chunk)

    return h.hexdigest()


def json_bytes(value) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    ).encode("utf-8")


def read_json(path: Path):
    return json.loads(
        Path(path).read_text(
            encoding="utf-8"
        )
    )


def safe_filename(value: str) -> str:
    if (
        not value
        or Path(value).name != value
        or "/" in value
        or "\\" in value
    ):
        raise RuntimeError(
            "UNSAFE_ARTIFACT_FILENAME"
        )

    return value


def supply_chain_digest(root: Path) -> str:
    return sha256_file(
        Path(root)
        / "supply-chain.lock.json"
    )


def git_output(
    root: Path,
    *args: str,
) -> str:
    return subprocess.check_output(
        [
            "git",
            "-C",
            str(root),
            *args,
        ],
        text=True,
    ).strip()


def create_wsp_archive(
    wsp_root: Path,
    commit: str,
    output: Path,
):
    wsp_root = Path(
        wsp_root
    )

    if git_output(
        wsp_root,
        "rev-parse",
        "HEAD",
    ) != commit:
        raise RuntimeError(
            "WSP_COMMIT_MISMATCH"
        )

    if git_output(
        wsp_root,
        "status",
        "--porcelain",
    ):
        raise RuntimeError(
            "WSP_SOURCE_DIRTY"
        )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output.open("wb") as handle:
        subprocess.run(
            [
                "git",
                "-C",
                str(wsp_root),
                "archive",
                "--format=tar",
                "--prefix=wam-silent-payments/",
                commit,
            ],
            check=True,
            stdout=handle,
        )


def download_wheel(
    python: str,
    name: str,
    version: str,
    wheelhouse: Path,
):
    wheelhouse.mkdir(
        parents=True,
        exist_ok=True,
    )

    with tempfile.TemporaryDirectory() as tmp:
        temp = Path(tmp)

        subprocess.run(
            [
                python,
                "-m",
                "pip",
                "download",
                "--disable-pip-version-check",
                "--only-binary=:all:",
                "--no-deps",
                "--dest",
                str(temp),
                f"{name}=={version}",
            ],
            check=True,
        )

        files = [
            item
            for item in temp.iterdir()
            if item.is_file()
        ]

        if len(files) != 1:
            raise RuntimeError(
                f"WHEEL_DOWNLOAD_COUNT:"
                f"{name}=={version}:"
                f"{len(files)}"
            )

        source = files[0]

        if source.suffix != ".whl":
            raise RuntimeError(
                "NON_WHEEL_ARTIFACT:"
                + source.name
            )

        target = (
            wheelhouse
            / safe_filename(
                source.name
            )
        )

        if target.exists():
            if (
                sha256_file(target)
                != sha256_file(source)
            ):
                raise RuntimeError(
                    "WHEEL_COLLISION:"
                    + target.name
                )

        else:
            shutil.move(
                str(source),
                str(target),
            )

        return target


def requirement_text(
    wheels,
) -> str:
    lines = []

    for item in sorted(
        wheels,
        key=lambda value: (
            canonical_name(
                value["name"]
            ),
            value["version"],
        ),
    ):
        # Do not ask pip to replace itself
        # during an offline environment test.
        if canonical_name(
            item["name"]
        ) == "pip":
            continue

        lines.append(
            f'{item["name"]}'
            f'=={item["version"]} '
            f'--hash=sha256:'
            f'{item["sha256"]}'
        )

    return (
        "\n".join(lines)
        + "\n"
    )


def build_sbom(
    artifact_lock,
):
    components = []

    for item in artifact_lock[
        "wheels"
    ]:
        name = item["name"]
        version = item["version"]

        components.append(
            {
                "type": "library",
                "name": name,
                "version": version,
                "purl": (
                    "pkg:pypi/"
                    + canonical_name(name)
                    + "@"
                    + version
                ),
                "hashes": [
                    {
                        "alg": "SHA-256",
                        "content": (
                            item["sha256"]
                        ),
                    }
                ],
            }
        )

    wsp = artifact_lock[
        "wam_silent_payments"
    ]

    components.append(
        {
            "type": "library",
            "name": (
                "wam-silent-payments"
            ),
            "version": wsp[
                "version"
            ],
            "properties": [
                {
                    "name": "git.commit",
                    "value": wsp[
                        "commit"
                    ],
                }
            ],
            "hashes": [
                {
                    "alg": "SHA-256",
                    "content": wsp[
                        "sha256"
                    ],
                }
            ],
        }
    )

    components.sort(
        key=lambda item: (
            item["name"],
            item.get(
                "version",
                "",
            ),
        )
    )

    digest = hashlib.sha256(
        json_bytes(
            artifact_lock
        )
    ).hexdigest()

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": (
            "urn:uuid:"
            + digest[0:8]
            + "-"
            + digest[8:12]
            + "-"
            + digest[12:16]
            + "-"
            + digest[16:20]
            + "-"
            + digest[20:32]
        ),
        "version": 1,
        "components": components,
    }


def build(
    root: Path,
    wsp_root: Path,
    wheelhouse: Path,
):
    root = Path(root)

    supply = read_json(
        root
        / "supply-chain.lock.json"
    )

    wheelhouse = Path(
        wheelhouse
    )

    shutil.rmtree(
        wheelhouse,
        ignore_errors=True,
    )

    wheelhouse.mkdir(
        parents=True,
        exist_ok=True,
    )

    wheel_records = []

    for distribution in supply[
        "distributions"
    ]:
        wheel = download_wheel(
            sys.executable,
            distribution["name"],
            distribution["version"],
            wheelhouse,
        )

        wheel_records.append(
            {
                "name": (
                    distribution["name"]
                ),
                "version": (
                    distribution["version"]
                ),
                "filename": (
                    wheel.name
                ),
                "sha256": (
                    sha256_file(
                        wheel
                    )
                ),
                "size": (
                    wheel.stat().st_size
                ),
            }
        )

    wsp = supply[
        "wam_silent_payments"
    ]

    commit = wsp[
        "commit"
    ]

    archive_name = (
        "wam-silent-payments-"
        + commit
        + ".tar"
    )

    archive = (
        root
        / "vendor"
        / archive_name
    )

    create_wsp_archive(
        wsp_root,
        commit,
        archive,
    )

    result = {
        "schema": SCHEMA_VERSION,
        "supply_chain_lock_sha256": (
            supply_chain_digest(
                root
            )
        ),
        "wam_silent_payments": {
            "version": wsp[
                "version"
            ],
            "commit": commit,
            "filename": (
                archive.name
            ),
            "sha256": (
                sha256_file(
                    archive
                )
            ),
            "size": (
                archive.stat().st_size
            ),
        },
        "wheels": sorted(
            wheel_records,
            key=lambda item: (
                canonical_name(
                    item["name"]
                ),
                item["version"],
            ),
        ),
    }

    return result


def verify(
    root: Path,
    lock,
) -> list[str]:
    root = Path(root)

    failures = []

    if (
        lock[
            "supply_chain_lock_sha256"
        ]
        != supply_chain_digest(
            root
        )
    ):
        failures.append(
            "supply-chain lock digest mismatch"
        )

    for wheel in lock[
        "wheels"
    ]:
        path = (
            root
            / "vendor"
            / "wheelhouse"
            / safe_filename(
                wheel["filename"]
            )
        )

        if not path.is_file():
            failures.append(
                "missing wheel: "
                + wheel["filename"]
            )

            continue

        if (
            path.stat().st_size
            != wheel["size"]
        ):
            failures.append(
                "wheel size mismatch: "
                + wheel["filename"]
            )

        if (
            sha256_file(path)
            != wheel["sha256"]
        ):
            failures.append(
                "wheel hash mismatch: "
                + wheel["filename"]
            )

    wsp = lock[
        "wam_silent_payments"
    ]

    archive = (
        root
        / "vendor"
        / safe_filename(
            wsp["filename"]
        )
    )

    if not archive.is_file():
        failures.append(
            "missing WSP archive"
        )

    else:
        if (
            archive.stat().st_size
            != wsp["size"]
        ):
            failures.append(
                "WSP archive size mismatch"
            )

        if (
            sha256_file(archive)
            != wsp["sha256"]
        ):
            failures.append(
                "WSP archive hash mismatch"
            )

    return failures


def main() -> int:
    parser = argparse.ArgumentParser()

    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    build_cmd = sub.add_parser(
        "build"
    )

    build_cmd.add_argument(
        "--root",
        default=".",
    )

    build_cmd.add_argument(
        "--wsp",
        default="../wam-silent-payments",
    )

    verify_cmd = sub.add_parser(
        "verify"
    )

    verify_cmd.add_argument(
        "--root",
        default=".",
    )

    args = parser.parse_args()

    root = Path(
        args.root
    ).resolve()

    try:
        if args.command == "build":
            lock = build(
                root,
                Path(args.wsp),
                root
                / "vendor"
                / "wheelhouse",
            )

            (
                root
                / "artifacts.lock.json"
            ).write_bytes(
                json_bytes(
                    lock
                )
            )

            (
                root
                / "requirements-hashed.txt"
            ).write_text(
                requirement_text(
                    lock["wheels"]
                ),
                encoding="utf-8",
            )

            (
                root
                / "sbom.cdx.json"
            ).write_bytes(
                json_bytes(
                    build_sbom(
                        lock
                    )
                )
            )

            print(
                "ARTIFACT LOCK BUILD: PASS"
            )

            print(
                "Artifacts:",
                len(
                    lock["wheels"]
                ),
                "wheel(s)",
            )

            print(
                "Lock SHA256:",
                sha256_file(
                    root
                    / "artifacts.lock.json"
                ),
            )

            return 0

        lock = read_json(
            root
            / "artifacts.lock.json"
        )

        failures = verify(
            root,
            lock,
        )

        expected_requirements = (
            requirement_text(
                lock["wheels"]
            )
        )

        actual_requirements = (
            root
            / "requirements-hashed.txt"
        ).read_text(
            encoding="utf-8"
        )

        if (
            expected_requirements
            != actual_requirements
        ):
            failures.append(
                "requirements-hashed.txt mismatch"
            )

        expected_sbom = json_bytes(
            build_sbom(
                lock
            )
        )

        actual_sbom = (
            root
            / "sbom.cdx.json"
        ).read_bytes()

        if (
            expected_sbom
            != actual_sbom
        ):
            failures.append(
                "SBOM mismatch"
            )

        if failures:
            print(
                "ARTIFACT LOCK VERIFY: FAIL"
            )

            for failure in failures:
                print(
                    " -",
                    failure,
                )

            return 1

        print(
            "ARTIFACT LOCK VERIFY: PASS"
        )

        print(
            "WHEELHOUSE BYTE INTEGRITY: PASS"
        )

        print(
            "WSP SOURCE ARCHIVE INTEGRITY: PASS"
        )

        print(
            "CYCLONEDX SBOM: PASS"
        )

        return 0

    except (
        KeyError,
        OSError,
        RuntimeError,
        subprocess.CalledProcessError,
    ) as exc:
        print(
            "ARTIFACT LOCK ERROR:",
            exc,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
