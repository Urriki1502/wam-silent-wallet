#!/usr/bin/env python3
"""Release artifact manifest for WAM Silent Wallet."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import subprocess

from scripts.reproducible_release import (
    app_manifest,
    canonical_json,
    manifest_digest,
)


REQUIRED_INPUTS = (
    "supply-chain.lock.json",
    "artifacts.lock.json",
    "requirements-hashed.txt",
    "sbom.cdx.json",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with Path(path).open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            h.update(chunk)

    return h.hexdigest()


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


def file_record(
    path: Path,
    root: Path,
) -> dict:
    path = Path(path).resolve()
    root = Path(root).resolve()

    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        relative = path.name

    if not path.is_file():
        raise RuntimeError(
            "RELEASE_ARTIFACT_MISSING:"
            + str(path)
        )

    return {
        "path": relative,
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def bundle_info(app: Path) -> dict:
    info_path = (
        Path(app)
        / "Contents"
        / "Info.plist"
    )

    if not info_path.is_file():
        raise RuntimeError(
            "APP_INFO_PLIST_MISSING"
        )

    with info_path.open("rb") as handle:
        info = plistlib.load(handle)

    return {
        "bundle_identifier": info.get(
            "CFBundleIdentifier",
            "",
        ),
        "bundle_name": info.get(
            "CFBundleName",
            "",
        ),
        "bundle_version": info.get(
            "CFBundleVersion",
            "",
        ),
    }


def create_manifest(
    *,
    root: Path,
    app: Path,
    artifacts: list[Path],
    version: str,
    signing_mode: str,
    notarized: bool,
) -> dict:
    root = Path(root).resolve()
    app = Path(app).resolve()

    inputs = {}

    for name in REQUIRED_INPUTS:
        path = root / name

        if not path.is_file():
            raise RuntimeError(
                "RELEASE_INPUT_MISSING:"
                + name
            )

        inputs[name] = file_record(
            path,
            root,
        )

    application_manifest = app_manifest(
        app
    )

    return {
        "schema": 1,
        "product": {
            "name": "WAM Silent Wallet",
            "version": version,
            **bundle_info(app),
        },
        "source": {
            "commit": git_output(
                root,
                "rev-parse",
                "HEAD",
            ),
            "tree": git_output(
                root,
                "rev-parse",
                "HEAD^{tree}",
            ),
        },
        "signing": {
            "mode": signing_mode,
            "notarized": bool(notarized),
        },
        "application": {
            "entries": len(
                application_manifest
            ),
            "manifest_sha256": (
                manifest_digest(
                    application_manifest
                )
            ),
        },
        "release_inputs": inputs,
        "artifacts": [
            file_record(
                item,
                root,
            )
            for item in artifacts
        ],
    }


def verify_manifest(
    root: Path,
    manifest: dict,
) -> list[str]:
    root = Path(root).resolve()
    failures = []

    for record in manifest[
        "release_inputs"
    ].values():
        path = root / record["path"]

        if not path.is_file():
            failures.append(
                "missing:"
                + record["path"]
            )
            continue

        if path.stat().st_size != record["size"]:
            failures.append(
                "size:"
                + record["path"]
            )

        if sha256_file(path) != record["sha256"]:
            failures.append(
                "sha256:"
                + record["path"]
            )

    for record in manifest[
        "artifacts"
    ]:
        path = root / record["path"]

        if not path.is_file():
            failures.append(
                "missing:"
                + record["path"]
            )
            continue

        if path.stat().st_size != record["size"]:
            failures.append(
                "size:"
                + record["path"]
            )

        if sha256_file(path) != record["sha256"]:
            failures.append(
                "sha256:"
                + record["path"]
            )

    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    create = sub.add_parser("create")
    create.add_argument("--root", default=".")
    create.add_argument("--app", required=True)
    create.add_argument(
        "--artifact",
        action="append",
        default=[],
    )
    create.add_argument(
        "--version",
        required=True,
    )
    create.add_argument(
        "--signing-mode",
        choices=(
            "adhoc",
            "developer-id",
        ),
        required=True,
    )
    create.add_argument(
        "--notarized",
        action="store_true",
    )
    create.add_argument(
        "--output",
        required=True,
    )

    verify = sub.add_parser("verify")
    verify.add_argument("--root", default=".")
    verify.add_argument(
        "--manifest",
        required=True,
    )

    args = parser.parse_args()

    try:
        root = Path(args.root).resolve()

        if args.command == "create":
            manifest = create_manifest(
                root=root,
                app=Path(args.app),
                artifacts=[
                    Path(item)
                    for item in args.artifact
                ],
                version=args.version,
                signing_mode=args.signing_mode,
                notarized=args.notarized,
            )

            output = Path(args.output)
            output.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            output.write_bytes(
                canonical_json(manifest)
            )

            print(
                "RELEASE MANIFEST CREATE: PASS"
            )
            print("Output:", output)
            return 0

        manifest = json.loads(
            Path(args.manifest).read_text(
                encoding="utf-8"
            )
        )

        failures = verify_manifest(
            root,
            manifest,
        )

        if failures:
            print(
                "RELEASE MANIFEST VERIFY: FAIL"
            )
            for failure in failures:
                print(" -", failure)
            return 1

        print(
            "RELEASE MANIFEST VERIFY: PASS"
        )
        return 0

    except (
        OSError,
        RuntimeError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
    ) as exc:
        print(
            "RELEASE MANIFEST ERROR:",
            exc,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
