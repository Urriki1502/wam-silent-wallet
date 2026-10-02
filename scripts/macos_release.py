#!/usr/bin/env python3
"""macOS Developer ID, notarization, stapling, and release evidence tooling."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys


class ReleaseError(RuntimeError):
    pass


def canonical_json(value) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bundle_manifest_digest(root: Path) -> str:
    root = Path(root)
    if not root.is_dir():
        raise ReleaseError(f"APP_BUNDLE_NOT_FOUND:{root}")

    digest = hashlib.sha256()

    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        mode = stat.S_IMODE(path.lstat().st_mode)

        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(mode).encode("ascii"))
        digest.update(b"\0")

        if path.is_symlink():
            digest.update(b"symlink\0")
            digest.update(os.readlink(path).encode("utf-8"))
        elif path.is_file():
            digest.update(b"file\0")
            digest.update(sha256_file(path).encode("ascii"))
        elif path.is_dir():
            digest.update(b"directory\0")

        digest.update(b"\n")

    return digest.hexdigest()


def run_command(args: list[str], *, capture: bool = False) -> str:
    printable = shlex.join(str(item) for item in args)
    print("+", printable)

    completed = subprocess.run(
        [str(item) for item in args],
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        text=True,
        check=False,
    )

    if completed.returncode != 0:
        output = completed.stdout or ""
        if output:
            print(output, file=sys.stderr)
        raise ReleaseError(
            f"COMMAND_FAILED:{completed.returncode}:{args[0]}"
        )

    return completed.stdout or ""


def parse_codesign_details(text: str) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        values.setdefault(key, []).append(value)

    return values


def last_value(
    details: dict[str, list[str]],
    key: str,
) -> str:
    values = details.get(key, [])
    return values[-1] if values else ""


def validate_release_signature(
    details: dict[str, list[str]],
    *,
    team_id: str,
    bundle_id: str,
) -> None:
    identifier = last_value(details, "Identifier")
    team = last_value(details, "TeamIdentifier")
    flags = " ".join(details.get("flags", []))
    signature = last_value(details, "Signature")
    timestamp = last_value(details, "Timestamp")
    authorities = details.get("Authority", [])

    if identifier != bundle_id:
        raise ReleaseError(
            f"BUNDLE_ID_MISMATCH:{identifier}:{bundle_id}"
        )

    if team != team_id:
        raise ReleaseError(
            f"TEAM_ID_MISMATCH:{team}:{team_id}"
        )

    if signature.lower() == "adhoc":
        raise ReleaseError("ADHOC_SIGNATURE_NOT_RELEASEABLE")

    if not any(
        authority.startswith("Developer ID Application:")
        for authority in authorities
    ):
        raise ReleaseError("DEVELOPER_ID_AUTHORITY_MISSING")

    if "runtime" not in flags:
        raise ReleaseError("HARDENED_RUNTIME_MISSING")

    if not timestamp:
        raise ReleaseError("SECURE_TIMESTAMP_MISSING")


def read_codesign_details(path: Path) -> tuple[str, dict[str, list[str]]]:
    text = run_command(
        [
            "/usr/bin/codesign",
            "--display",
            "--verbose=4",
            str(path),
        ],
        capture=True,
    )
    return text, parse_codesign_details(text)


def verify_app(
    app: Path,
    *,
    team_id: str,
    bundle_id: str,
    gatekeeper: bool,
) -> dict:
    app = Path(app)

    if not app.is_dir():
        raise ReleaseError(f"APP_BUNDLE_NOT_FOUND:{app}")

    run_command(
        [
            "/usr/bin/codesign",
            "--verify",
            "--deep",
            "--strict",
            "--verbose=4",
            str(app),
        ]
    )

    raw, details = read_codesign_details(app)

    validate_release_signature(
        details,
        team_id=team_id,
        bundle_id=bundle_id,
    )

    if gatekeeper:
        run_command(
            [
                "/usr/sbin/spctl",
                "--assess",
                "--type",
                "execute",
                "--verbose=4",
                str(app),
            ]
        )

    return {
        "bundle_id": bundle_id,
        "team_id": team_id,
        "manifest_sha256": bundle_manifest_digest(app),
        "codesign": details,
        "codesign_raw": raw,
        "gatekeeper_checked": gatekeeper,
    }


def create_dmg(
    app: Path,
    output: Path,
    *,
    volume_name: str,
) -> None:
    app = Path(app)
    output = Path(output)

    if not app.is_dir():
        raise ReleaseError(f"APP_BUNDLE_NOT_FOUND:{app}")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)

    run_command(
        [
            "/usr/bin/hdiutil",
            "create",
            "-volname",
            volume_name,
            "-srcfolder",
            str(app),
            "-ov",
            "-format",
            "UDZO",
            str(output),
        ]
    )

    if not output.is_file():
        raise ReleaseError(f"DMG_NOT_CREATED:{output}")


def sign_dmg(
    dmg: Path,
    *,
    identity: str,
) -> None:
    dmg = Path(dmg)

    if not dmg.is_file():
        raise ReleaseError(f"DMG_NOT_FOUND:{dmg}")

    if not identity.startswith("Developer ID Application:"):
        raise ReleaseError("INVALID_DEVELOPER_IDENTITY")

    run_command(
        [
            "/usr/bin/codesign",
            "--force",
            "--timestamp",
            "--sign",
            identity,
            str(dmg),
        ]
    )

    run_command(
        [
            "/usr/bin/codesign",
            "--verify",
            "--strict",
            "--verbose=4",
            str(dmg),
        ]
    )


def notarize(
    dmg: Path,
    *,
    key: Path,
    key_id: str,
    issuer: str,
    output: Path,
) -> dict:
    dmg = Path(dmg)
    key = Path(key)
    output = Path(output)

    if not dmg.is_file():
        raise ReleaseError(f"DMG_NOT_FOUND:{dmg}")

    if not key.is_file():
        raise ReleaseError(f"NOTARY_KEY_NOT_FOUND:{key}")

    response = run_command(
        [
            "/usr/bin/xcrun",
            "notarytool",
            "submit",
            str(dmg),
            "--key",
            str(key),
            "--key-id",
            key_id,
            "--issuer",
            issuer,
            "--wait",
            "--output-format",
            "json",
        ],
        capture=True,
    )

    try:
        data = json.loads(response)
    except json.JSONDecodeError as exc:
        raise ReleaseError("NOTARY_RESPONSE_NOT_JSON") from exc

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_json(data))

    if data.get("status") != "Accepted":
        submission_id = data.get("id")
        if submission_id:
            try:
                log_text = run_command(
                    [
                        "/usr/bin/xcrun",
                        "notarytool",
                        "log",
                        str(submission_id),
                        "--key",
                        str(key),
                        "--key-id",
                        key_id,
                        "--issuer",
                        issuer,
                    ],
                    capture=True,
                )
                print(log_text)
            except ReleaseError:
                pass

        raise ReleaseError(
            "NOTARIZATION_NOT_ACCEPTED:"
            + str(data.get("status"))
        )

    return data


def staple_verify(dmg: Path) -> None:
    dmg = Path(dmg)

    run_command(
        [
            "/usr/bin/xcrun",
            "stapler",
            "staple",
            str(dmg),
        ]
    )

    run_command(
        [
            "/usr/bin/xcrun",
            "stapler",
            "validate",
            str(dmg),
        ]
    )

    run_command(
        [
            "/usr/sbin/spctl",
            "--assess",
            "--type",
            "open",
            "--context",
            "context:primary-signature",
            "--verbose=4",
            str(dmg),
        ]
    )


def write_evidence(
    *,
    app: Path,
    dmg: Path,
    team_id: str,
    bundle_id: str,
    notarization: Path,
    output: Path,
) -> dict:
    app = Path(app)
    dmg = Path(dmg)
    notarization = Path(notarization)
    output = Path(output)

    if not dmg.is_file():
        raise ReleaseError(f"DMG_NOT_FOUND:{dmg}")

    if not notarization.is_file():
        raise ReleaseError(
            f"NOTARIZATION_EVIDENCE_NOT_FOUND:{notarization}"
        )

    notary = json.loads(
        notarization.read_text(encoding="utf-8")
    )

    if notary.get("status") != "Accepted":
        raise ReleaseError("NOTARIZATION_EVIDENCE_NOT_ACCEPTED")

    app_evidence = verify_app(
        app,
        team_id=team_id,
        bundle_id=bundle_id,
        gatekeeper=False,
    )

    _, dmg_details = read_codesign_details(dmg)

    result = {
        "schema": 1,
        "source": {
            "github_sha": os.environ.get("GITHUB_SHA", ""),
            "github_ref": os.environ.get("GITHUB_REF", ""),
        },
        "app": app_evidence,
        "dmg": {
            "filename": dmg.name,
            "size": dmg.stat().st_size,
            "sha256": sha256_file(dmg),
            "codesign": dmg_details,
        },
        "notarization": {
            "id": notary.get("id"),
            "status": notary.get("status"),
            "message": notary.get("message"),
        },
        "qualification": {
            "developer_id": True,
            "hardened_runtime": True,
            "secure_timestamp": True,
            "notarized": True,
            "stapled": True,
            "gatekeeper_dmg": True,
        },
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_json(result))
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    verify = sub.add_parser("verify-app")
    verify.add_argument("--app", required=True)
    verify.add_argument("--team-id", required=True)
    verify.add_argument("--bundle-id", required=True)
    verify.add_argument(
        "--gatekeeper",
        action="store_true",
    )

    dmg = sub.add_parser("create-dmg")
    dmg.add_argument("--app", required=True)
    dmg.add_argument("--output", required=True)
    dmg.add_argument(
        "--volume-name",
        default="WAM Silent Wallet",
    )

    sign = sub.add_parser("sign-dmg")
    sign.add_argument("--dmg", required=True)
    sign.add_argument("--identity", required=True)

    note = sub.add_parser("notarize")
    note.add_argument("--dmg", required=True)
    note.add_argument("--key", required=True)
    note.add_argument("--key-id", required=True)
    note.add_argument("--issuer", required=True)
    note.add_argument("--output", required=True)

    staple = sub.add_parser("staple-verify")
    staple.add_argument("--dmg", required=True)

    evidence = sub.add_parser("evidence")
    evidence.add_argument("--app", required=True)
    evidence.add_argument("--dmg", required=True)
    evidence.add_argument("--team-id", required=True)
    evidence.add_argument("--bundle-id", required=True)
    evidence.add_argument("--notarization", required=True)
    evidence.add_argument("--output", required=True)

    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        if args.command == "verify-app":
            result = verify_app(
                Path(args.app),
                team_id=args.team_id,
                bundle_id=args.bundle_id,
                gatekeeper=args.gatekeeper,
            )
            print(
                "MACOS APP SIGNATURE: PASS",
                result["manifest_sha256"],
            )

        elif args.command == "create-dmg":
            create_dmg(
                Path(args.app),
                Path(args.output),
                volume_name=args.volume_name,
            )
            print("DMG CREATE: PASS")

        elif args.command == "sign-dmg":
            sign_dmg(
                Path(args.dmg),
                identity=args.identity,
            )
            print("DMG SIGNATURE: PASS")

        elif args.command == "notarize":
            result = notarize(
                Path(args.dmg),
                key=Path(args.key),
                key_id=args.key_id,
                issuer=args.issuer,
                output=Path(args.output),
            )
            print(
                "NOTARIZATION: PASS",
                result.get("id"),
            )

        elif args.command == "staple-verify":
            staple_verify(Path(args.dmg))
            print("STAPLE / GATEKEEPER: PASS")

        elif args.command == "evidence":
            result = write_evidence(
                app=Path(args.app),
                dmg=Path(args.dmg),
                team_id=args.team_id,
                bundle_id=args.bundle_id,
                notarization=Path(args.notarization),
                output=Path(args.output),
            )
            print(
                "MACOS RELEASE EVIDENCE: PASS",
                result["dmg"]["sha256"],
            )

        else:
            raise ReleaseError("UNKNOWN_COMMAND")

        return 0

    except (
        ReleaseError,
        OSError,
        subprocess.SubprocessError,
        json.JSONDecodeError,
    ) as exc:
        print(
            "MACOS RELEASE ERROR:",
            exc,
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
