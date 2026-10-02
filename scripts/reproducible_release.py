#!/usr/bin/env python3
"""Reproducible release comparison and provenance tooling."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess


def sha256_file(
    path: Path,
) -> str:
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


def canonical_json(
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
    ).encode("utf-8")


def app_manifest(
    root: Path,
):
    root = Path(root)

    if not root.is_dir():
        raise RuntimeError(
            "APP_BUNDLE_NOT_FOUND:"
            + str(root)
        )

    result = {}

    for path in sorted(
        root.rglob("*")
    ):
        relative = (
            path
            .relative_to(root)
            .as_posix()
        )

        mode = stat.S_IMODE(
            path.lstat().st_mode
        )

        if path.is_symlink():
            result[relative] = {
                "type": "symlink",
                "mode": mode,
                "target": os.readlink(
                    path
                ),
            }

        elif path.is_file():
            result[relative] = {
                "type": "file",
                "mode": mode,
                "size": path.stat().st_size,
                "sha256": sha256_file(
                    path
                ),
            }

        elif path.is_dir():
            result[relative] = {
                "type": "directory",
                "mode": mode,
            }

    return result


def manifest_digest(
    manifest,
) -> str:
    return hashlib.sha256(
        canonical_json(
            manifest
        )
    ).hexdigest()


def compare_manifests(
    a,
    b,
):
    differences = []

    for path in sorted(
        set(a)
        | set(b)
    ):
        if path not in a:
            differences.append(
                {
                    "path": path,
                    "reason": "missing-from-A",
                }
            )

        elif path not in b:
            differences.append(
                {
                    "path": path,
                    "reason": "missing-from-B",
                }
            )

        elif a[path] != b[path]:
            differences.append(
                {
                    "path": path,
                    "reason": "content-or-mode",
                    "A": a[path],
                    "B": b[path],
                }
            )

    return differences


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


def source_dirty(
    root: Path,
) -> bool:
    return bool(
        git_output(
            root,
            "status",
            "--porcelain",
        )
    )


def provenance(
    root: Path,
    app_a: Path,
    app_b: Path,
    *,
    require_clean: bool,
):
    root = Path(root).resolve()

    ma = app_manifest(
        app_a
    )

    mb = app_manifest(
        app_b
    )

    differences = compare_manifests(
        ma,
        mb,
    )

    if differences:
        raise RuntimeError(
            "REPRODUCIBLE_BUILD_MISMATCH"
        )

    if (
        require_clean
        and source_dirty(root)
    ):
        raise RuntimeError(
            "SOURCE_REPOSITORY_DIRTY"
        )

    required = [
        "supply-chain.lock.json",
        "artifacts.lock.json",
        "requirements-hashed.txt",
        "sbom.cdx.json",
    ]

    inputs = {}

    for name in required:
        path = root / name

        if not path.is_file():
            raise RuntimeError(
                "RELEASE_INPUT_MISSING:"
                + name
            )

        inputs[name] = {
            "sha256": sha256_file(
                path
            ),
            "size": path.stat().st_size,
        }

    digest = manifest_digest(
        ma
    )

    return {
        "schema": 1,
        "source": {
            "commit": git_output(
                root,
                "rev-parse",
                "HEAD",
            ),
            "branch": git_output(
                root,
                "branch",
                "--show-current",
            ),
            "dirty": source_dirty(
                root
            ),
        },
        "reproducible_build": {
            "entries": len(ma),
            "manifest_sha256": digest,
            "build_a_sha256": digest,
            "build_b_sha256": digest,
            "identical": True,
        },
        "release_inputs": inputs,
    }


def command_compare(
    args,
) -> int:
    ma = app_manifest(
        Path(args.a)
    )

    mb = app_manifest(
        Path(args.b)
    )

    differences = compare_manifests(
        ma,
        mb,
    )

    ha = manifest_digest(
        ma
    )

    hb = manifest_digest(
        mb
    )

    print(
        "Build A manifest:",
        ha,
    )

    print(
        "Build B manifest:",
        hb,
    )

    print(
        "Entries A:",
        len(ma),
    )

    print(
        "Entries B:",
        len(mb),
    )

    print(
        "Differences:",
        len(differences),
    )

    if args.output:
        Path(
            args.output
        ).parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        Path(
            args.output
        ).write_bytes(
            canonical_json(
                {
                    "build_a": ha,
                    "build_b": hb,
                    "entries_a": len(ma),
                    "entries_b": len(mb),
                    "differences": differences,
                }
            )
        )

    if differences:
        print(
            "REPRODUCIBLE RELEASE COMPARE: FAIL"
        )

        return 1

    print(
        "FILE TREE IDENTICAL: PASS"
    )

    print(
        "FILE MODES IDENTICAL: PASS"
    )

    print(
        "ALL FILE SHA256 IDENTICAL: PASS"
    )

    print(
        "REPRODUCIBLE RELEASE COMPARE: PASS"
    )

    return 0


def command_provenance(
    args,
) -> int:
    result = provenance(
        Path(args.root),
        Path(args.a),
        Path(args.b),
        require_clean=(
            args.require_clean
        ),
    )

    output = Path(
        args.output
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_bytes(
        canonical_json(
            result
        )
    )

    print(
        "RELEASE PROVENANCE: PASS"
    )

    print(
        "Manifest SHA256:",
        result[
            "reproducible_build"
        ][
            "manifest_sha256"
        ],
    )

    print(
        "Output:",
        output,
    )

    return 0


def main() -> int:
    parser = argparse.ArgumentParser()

    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    compare = sub.add_parser(
        "compare"
    )

    compare.add_argument(
        "--a",
        required=True,
    )

    compare.add_argument(
        "--b",
        required=True,
    )

    compare.add_argument(
        "--output",
    )

    compare.set_defaults(
        func=command_compare
    )

    prov = sub.add_parser(
        "provenance"
    )

    prov.add_argument(
        "--root",
        default=".",
    )

    prov.add_argument(
        "--a",
        required=True,
    )

    prov.add_argument(
        "--b",
        required=True,
    )

    prov.add_argument(
        "--output",
        default=(
            ".release/"
            "release-provenance.json"
        ),
    )

    prov.add_argument(
        "--require-clean",
        action="store_true",
    )

    prov.set_defaults(
        func=command_provenance
    )

    args = parser.parse_args()

    try:
        return args.func(
            args
        )

    except (
        RuntimeError,
        OSError,
        subprocess.CalledProcessError,
    ) as exc:
        print(
            "REPRODUCIBLE RELEASE ERROR:",
            exc,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
