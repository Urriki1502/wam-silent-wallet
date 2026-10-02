#!/usr/bin/env python3
"""Release contamination gate for WAM Silent Wallet."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys


TEXT_SUFFIXES = {
    ".py",
    ".toml",
    ".json",
    ".txt",
    ".md",
    ".yml",
    ".yaml",
    ".sh",
}


BANNED_TRACKED_NAMES = {
    "wallet.db",
    "keys.wsp",
    ".cookie",
    ".wallet-runtime.lock",
    "wallet.db.scan.lock",
    "recovery-pending.json",
    ".recovery-activation.json",
    ".DS_Store",
}


BANNED_SOURCE_PATTERNS = (
    (
        "test-only environment flag",
        re.compile(
            r"\bWAM_TEST_[A-Z0-9_]+\b"
        ),
    ),
    (
        "macOS developer home",
        re.compile(
            r"/Users/"
            r"[A-Za-z0-9._-]+/"
        ),
    ),
    (
        "Linux developer home",
        re.compile(
            r"/home/"
            r"[A-Za-z0-9._-]+/"
        ),
    ),
    (
        "Windows developer home",
        re.compile(
            r"[A-Za-z]:"
            r"\\\\Users\\\\"
            r"[^\\\\\r\n]+\\\\"
        ),
    ),
    (
        "WAM temporary test runtime",
        re.compile(
            r"/tmp/"
            r"wam-[A-Za-z0-9._-]+"
        ),
    ),
    (
        "Python debugger breakpoint",
        re.compile(
            r"\bbreakpoint\s*\("
        ),
    ),
    (
        "pdb debugger",
        re.compile(
            r"\bpdb"
            r"\.set_trace\s*\("
        ),
    ),
    (
        "embedded private-key PEM",
        re.compile(
            r"-----BEGIN "
            r"(?:RSA |EC |OPENSSH )?"
            r"PRIVATE KEY-----"
        ),
    ),
)


def is_runtime_artifact(
    path: Path,
) -> bool:
    name = path.name

    if name in BANNED_TRACKED_NAMES:
        return True

    if name.endswith(
        ".wspbak"
    ):
        return True

    if name.startswith(
        "wallet.db-"
    ):
        return True

    if name.startswith(
        ".recovery-rollback-"
    ):
        return True

    return False


def tracked_files(
    root: Path,
) -> list[Path]:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "-z",
        ],
        check=True,
        stdout=subprocess.PIPE,
    )

    raw = result.stdout.split(
        b"\x00"
    )

    return [
        Path(
            item.decode(
                "utf-8",
                errors="strict",
            )
        )
        for item in raw
        if item
    ]


def scan_tracked_paths(
    paths,
) -> list[str]:
    findings = []

    for path in paths:
        path = Path(
            path
        )

        if is_runtime_artifact(
            path
        ):
            findings.append(
                "tracked runtime artifact: "
                + path.as_posix()
            )

    return findings


def release_files(
    root: Path,
):
    app = root / "app.py"

    if app.exists():
        yield app

    source = root / "src"

    if not source.exists():
        return

    for path in sorted(
        source.rglob("*")
    ):
        if (
            "__pycache__"
            in path.parts
        ):
            continue

        if (
            path.is_file()
            or path.is_symlink()
        ):
            yield path


def scan_release_tree(
    root: Path,
) -> list[str]:
    root = Path(
        root
    )

    findings = []

    for path in release_files(
        root
    ):
        relative = (
            path.relative_to(
                root
            )
        )

        if path.is_symlink():
            findings.append(
                "release symlink: "
                + relative.as_posix()
            )

            continue

        if is_runtime_artifact(
            path
        ):
            findings.append(
                "release runtime artifact: "
                + relative.as_posix()
            )

            continue

        if (
            path.suffix.lower()
            not in TEXT_SUFFIXES
            and path.name != "app.py"
        ):
            continue

        try:
            text = path.read_text(
                encoding="utf-8"
            )

        except (
            OSError,
            UnicodeError,
        ):
            continue

        for (
            description,
            pattern,
        ) in BANNED_SOURCE_PATTERNS:
            match = pattern.search(
                text
            )

            if match is None:
                continue

            line = (
                text.count(
                    "\n",
                    0,
                    match.start(),
                )
                + 1
            )

            findings.append(
                f"{description}: "
                f"{relative.as_posix()}:"
                f"{line}"
            )

    return findings


def run_scan(
    root: Path,
) -> list[str]:
    root = Path(
        root
    ).resolve()

    findings = []

    findings.extend(
        scan_tracked_paths(
            tracked_files(
                root
            )
        )
    )

    findings.extend(
        scan_release_tree(
            root
        )
    )

    return findings


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--root",
        default=".",
    )

    args = parser.parse_args()

    root = Path(
        args.root
    )

    findings = run_scan(
        root
    )

    if findings:
        print(
            "RELEASE INTEGRITY: FAIL"
        )

        for finding in findings:
            print(
                " -",
                finding,
            )

        return 1

    print(
        "RELEASE INTEGRITY: PASS"
    )

    print(
        "No wallet runtime artifacts,"
        " dev paths, failpoints,"
        " debugger hooks or embedded"
        " private-key PEM detected."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
