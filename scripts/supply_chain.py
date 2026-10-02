#!/usr/bin/env python3
"""Deterministic build-environment and source provenance lock."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tomllib

from packaging.requirements import Requirement


SCHEMA_VERSION = 1

PIN_RE = re.compile(
    r"^\s*"
    r"([A-Za-z0-9_.-]+)"
    r"=="
    r"([A-Za-z0-9_.+!-]+)"
    r"\s*$"
)

METADATA_FILES = (
    "METADATA",
    "WHEEL",
    "RECORD",
    "entry_points.txt",
    "top_level.txt",
)


def canonical_name(
    value: str,
) -> str:
    return re.sub(
        r"[-_.]+",
        "-",
        value,
    ).lower()


def sha256_bytes(
    value: bytes,
) -> str:
    return hashlib.sha256(
        value
    ).hexdigest()


def sha256_file(
    path: Path,
) -> str:
    return sha256_bytes(
        Path(path).read_bytes()
    )


def canonical_json_bytes(
    value,
) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    ).encode(
        "utf-8"
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


def git_is_dirty(
    root: Path,
) -> bool:
    return bool(
        git_output(
            root,
            "status",
            "--porcelain",
        )
    )


def project_version(
    pyproject: Path,
) -> str:
    data = tomllib.loads(
        pyproject.read_text(
            encoding="utf-8"
        )
    )

    return str(
        data["project"]["version"]
    )


def validate_exact_pins(
    pyproject: Path,
):
    data = tomllib.loads(
        Path(pyproject).read_text(
            encoding="utf-8"
        )
    )

    candidates = []

    for requirement in (
        data
        .get(
            "build-system",
            {},
        )
        .get(
            "requires",
            [],
        )
    ):
        candidates.append(
            (
                "build-system",
                requirement,
            )
        )

    for requirement in (
        data
        .get(
            "project",
            {},
        )
        .get(
            "dependencies",
            [],
        )
    ):
        candidates.append(
            (
                "project",
                requirement,
            )
        )

    failures = []

    for scope, requirement in candidates:
        if PIN_RE.fullmatch(
            requirement
        ) is None:
            failures.append(
                f"{scope}: {requirement}"
            )

    if failures:
        raise RuntimeError(
            "UNPINNED_DEPENDENCY: "
            + "; ".join(
                failures
            )
        )


def distribution_is_editable(
    distribution,
) -> bool:
    try:
        raw = distribution.read_text(
            "direct_url.json"
        )

    except Exception:
        return False

    if not raw:
        return False

    try:
        data = json.loads(
            raw
        )

    except json.JSONDecodeError:
        return False

    return bool(
        data
        .get(
            "dir_info",
            {},
        )
        .get(
            "editable",
            False,
        )
    )


def distribution_metadata_digest(
    distribution,
) -> str:
    h = hashlib.sha256()

    for name in METADATA_FILES:
        try:
            text = distribution.read_text(
                name
            )

        except Exception:
            text = None

        if text is None:
            continue

        h.update(
            name.encode(
                "utf-8"
            )
        )

        h.update(
            b"\0"
        )

        h.update(
            text.encode(
                "utf-8",
                errors="strict",
            )
        )

        h.update(
            b"\0"
        )

    return h.hexdigest()


def _active_requirement(
    raw: str,
):
    requirement = Requirement(
        raw
    )

    if (
        requirement.marker is not None
        and not requirement.marker.evaluate(
            {
                "extra": "",
            }
        )
    ):
        return None

    return requirement


def _project_requirement_roots(
    root: Path,
    wsp_root: Path,
):
    roots = set()

    wallet = tomllib.loads(
        (
            Path(root)
            / "pyproject.toml"
        ).read_text(
            encoding="utf-8"
        )
    )

    wsp = tomllib.loads(
        (
            Path(wsp_root)
            / "pyproject.toml"
        ).read_text(
            encoding="utf-8"
        )
    )

    raw_requirements = []

    raw_requirements.extend(
        wallet
        .get(
            "build-system",
            {},
        )
        .get(
            "requires",
            [],
        )
    )

    raw_requirements.extend(
        wallet
        .get(
            "project",
            {},
        )
        .get(
            "dependencies",
            [],
        )
    )

    raw_requirements.extend(
        wsp
        .get(
            "build-system",
            {},
        )
        .get(
            "requires",
            [],
        )
    )

    raw_requirements.extend(
        wsp
        .get(
            "project",
            {},
        )
        .get(
            "dependencies",
            [],
        )
    )

    # Release qualification/build tooling.
    # These are intentional roots even though they are not
    # runtime dependencies of the wallet itself.
    raw_requirements.extend(
        [
            "pytest",
            "PyInstaller",
        ]
    )

    for raw in raw_requirements:
        requirement = _active_requirement(
            raw
        )

        if requirement is None:
            continue

        roots.add(
            canonical_name(
                requirement.name
            )
        )

    return roots


def installed_distributions(
    root: Path,
    wsp_root: Path,
):
    """
    Lock only the transitive dependency closure needed to
    build/test/run WAM Silent Wallet + WSP.

    Do NOT snapshot arbitrary packages merely because they
    happen to be installed in the developer virtualenv.
    """

    queue = list(
        sorted(
            _project_requirement_roots(
                root,
                wsp_root,
            )
        )
    )

    seen = set()
    records = {}

    while queue:
        requested_name = queue.pop(
            0
        )

        name = canonical_name(
            requested_name
        )

        if name in seen:
            continue

        seen.add(
            name
        )

        try:
            distribution = (
                importlib.metadata.distribution(
                    requested_name
                )
            )

        except importlib.metadata.PackageNotFoundError as exc:
            raise RuntimeError(
                "REQUIRED_DISTRIBUTION_MISSING:"
                + requested_name
            ) from exc

        raw_name = (
            distribution.metadata.get(
                "Name"
            )
            or requested_name
        )

        canonical = canonical_name(
            raw_name
        )

        records[canonical] = {
            "name": raw_name,
            "version": distribution.version,
            "metadata_sha256": (
                distribution_metadata_digest(
                    distribution
                )
            ),
        }

        for raw_dependency in (
            distribution.requires
            or []
        ):
            requirement = _active_requirement(
                raw_dependency
            )

            if requirement is None:
                continue

            dependency_name = canonical_name(
                requirement.name
            )

            if dependency_name not in seen:
                queue.append(
                    dependency_name
                )

    return [
        records[name]
        for name in sorted(
            records
        )
    ]

def source_identity(
    root: Path,
    *,
    require_clean: bool = True,
):
    root = Path(
        root
    ).resolve()

    if not (
        root / ".git"
    ).exists():
        raise RuntimeError(
            "SOURCE_REPOSITORY_NOT_FOUND"
        )

    commit = git_output(
        root,
        "rev-parse",
        "HEAD",
    )

    if not re.fullmatch(
        r"[0-9a-f]{40}",
        commit,
    ):
        raise RuntimeError(
            "SOURCE_COMMIT_INVALID"
        )

    dirty = git_is_dirty(
        root
    )

    if (
        require_clean
        and dirty
    ):
        raise RuntimeError(
            "SOURCE_REPOSITORY_DIRTY"
        )

    pyproject = (
        root
        / "pyproject.toml"
    )

    if not pyproject.is_file():
        raise RuntimeError(
            "SOURCE_PYPROJECT_MISSING"
        )

    return {
        "commit": commit,
        "version": project_version(
            pyproject
        ),
    }


def project_inputs(
    root: Path,
):
    root = Path(
        root
    )

    paths = [
        Path(
            "pyproject.toml"
        ),
        Path(
            "packaging/hooks/"
            "hook-coincurve.py"
        ),
        Path(
            "scripts/"
            "release_integrity.py"
        ),
    ]

    result = {}

    for relative in paths:
        path = (
            root
            / relative
        )

        if not path.is_file():
            continue

        result[
            relative.as_posix()
        ] = sha256_file(
            path
        )

    return result


def build_manifest(
    root: Path,
    wsp_root: Path,
    *,
    require_wsp_clean: bool = True,
):
    root = Path(
        root
    ).resolve()

    validate_exact_pins(
        root
        / "pyproject.toml"
    )

    wsp = source_identity(
        wsp_root,
        require_clean=require_wsp_clean,
    )

    return {
        "schema": SCHEMA_VERSION,
        "python": {
            "implementation": (
                platform.python_implementation()
            ),
            "version": (
                platform.python_version()
            ),
            "cache_tag": (
                sys.implementation.cache_tag
            ),
        },
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
        },
        "project_inputs": (
            project_inputs(
                root
            )
        ),
        "wam_silent_payments": {
            "repository": (
                "https://github.com/"
                "Urriki1502/"
                "wam-silent-payments.git"
            ),
            **wsp,
        },
        "distributions": (
            installed_distributions(
                root,
                wsp_root,
            )
        ),
    }


def manifest_diff(
    expected,
    actual,
    path: str = "",
):
    differences = []

    if type(expected) is not type(actual):
        return [
            f"{path or '<root>'}: "
            f"type mismatch"
        ]

    if isinstance(
        expected,
        dict,
    ):
        keys = sorted(
            set(expected)
            | set(actual)
        )

        for key in keys:
            child = (
                f"{path}.{key}"
                if path
                else str(key)
            )

            if key not in expected:
                differences.append(
                    child
                    + ": unexpected"
                )

                continue

            if key not in actual:
                differences.append(
                    child
                    + ": missing"
                )

                continue

            differences.extend(
                manifest_diff(
                    expected[key],
                    actual[key],
                    child,
                )
            )

        return differences

    if isinstance(
        expected,
        list,
    ):
        if expected != actual:
            differences.append(
                f"{path}: list mismatch"
            )

        return differences

    if expected != actual:
        differences.append(
            f"{path}: "
            f"{expected!r} != "
            f"{actual!r}"
        )

    return differences


def write_manifest(
    path: Path,
    manifest,
):
    path = Path(
        path
    )

    data = canonical_json_bytes(
        manifest
    )

    path.write_bytes(
        data
    )

    return sha256_bytes(
        data
    )


def read_manifest(
    path: Path,
):
    return json.loads(
        Path(path).read_text(
            encoding="utf-8"
        )
    )


def cmd_snapshot(
    args,
) -> int:
    manifest = build_manifest(
        Path(args.root),
        Path(args.wsp),
        require_wsp_clean=(
            not args.allow_dirty_wsp
        ),
    )

    digest = write_manifest(
        Path(args.output),
        manifest,
    )

    print(
        "SUPPLY CHAIN SNAPSHOT: PASS"
    )

    print(
        "Manifest:",
        args.output,
    )

    print(
        "SHA256:",
        digest,
    )

    return 0


def cmd_verify(
    args,
) -> int:
    expected = read_manifest(
        Path(args.lock)
    )

    actual = build_manifest(
        Path(args.root),
        Path(args.wsp),
        require_wsp_clean=True,
    )

    differences = manifest_diff(
        expected,
        actual,
    )

    if differences:
        print(
            "SUPPLY CHAIN VERIFY: FAIL"
        )

        for difference in differences[:100]:
            print(
                " -",
                difference,
            )

        return 1

    digest = sha256_bytes(
        canonical_json_bytes(
            actual
        )
    )

    print(
        "SUPPLY CHAIN VERIFY: PASS"
    )

    print(
        "Manifest SHA256:",
        digest,
    )

    return 0


def cmd_audit_pins(
    args,
) -> int:
    validate_exact_pins(
        Path(args.root)
        / "pyproject.toml"
    )

    print(
        "EXACT DEPENDENCY PINS: PASS"
    )

    return 0


def main() -> int:
    parser = argparse.ArgumentParser()

    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    snapshot = sub.add_parser(
        "snapshot"
    )

    snapshot.add_argument(
        "--root",
        default=".",
    )

    snapshot.add_argument(
        "--wsp",
        default="../wam-silent-payments",
    )

    snapshot.add_argument(
        "--output",
        default="supply-chain.lock.json",
    )

    snapshot.add_argument(
        "--allow-dirty-wsp",
        action="store_true",
    )

    snapshot.set_defaults(
        func=cmd_snapshot
    )

    verify = sub.add_parser(
        "verify"
    )

    verify.add_argument(
        "--root",
        default=".",
    )

    verify.add_argument(
        "--wsp",
        default="../wam-silent-payments",
    )

    verify.add_argument(
        "--lock",
        default="supply-chain.lock.json",
    )

    verify.set_defaults(
        func=cmd_verify
    )

    audit = sub.add_parser(
        "audit-pins"
    )

    audit.add_argument(
        "--root",
        default=".",
    )

    audit.set_defaults(
        func=cmd_audit_pins
    )

    args = parser.parse_args()

    try:
        return args.func(
            args
        )

    except (
        RuntimeError,
        OSError,
        KeyError,
        ValueError,
    ) as exc:
        print(
            "SUPPLY CHAIN ERROR:",
            str(exc),
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
