from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "macos_release.py"

SPEC = importlib.util.spec_from_file_location(
    "macos_release",
    SCRIPT,
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


SAMPLE = """
Executable=/tmp/WAM Silent Wallet.app/Contents/MacOS/WAM Silent Wallet
Identifier=org.wamcoin.silentwallet
Format=app bundle with Mach-O thin (arm64)
CodeDirectory v=20500 size=123 flags=0x10000(runtime) hashes=3+7 location=embedded
Signature size=9055
Authority=Developer ID Application: Example Developer (TEAM123456)
Authority=Developer ID Certification Authority
Authority=Apple Root CA
Timestamp=Oct 2, 2026 at 20:00:00
TeamIdentifier=TEAM123456
"""


def test_parse_codesign_details_keeps_authority_chain():
    details = MODULE.parse_codesign_details(SAMPLE)

    assert details["Identifier"] == [
        "org.wamcoin.silentwallet"
    ]
    assert len(details["Authority"]) == 3
    assert details["TeamIdentifier"] == [
        "TEAM123456"
    ]


def test_release_signature_accepts_developer_id_runtime():
    details = MODULE.parse_codesign_details(SAMPLE)

    MODULE.validate_release_signature(
        details,
        team_id="TEAM123456",
        bundle_id="org.wamcoin.silentwallet",
    )


@pytest.mark.parametrize(
    "replacement,expected",
    [
        (
            "flags=0x0(none)",
            "HARDENED_RUNTIME_MISSING",
        ),
        (
            "Signature=adhoc",
            "ADHOC_SIGNATURE_NOT_RELEASEABLE",
        ),
        (
            "TeamIdentifier=WRONGTEAM",
            "TEAM_ID_MISMATCH",
        ),
        (
            "Identifier=org.example.wrong",
            "BUNDLE_ID_MISMATCH",
        ),
    ],
)
def test_release_signature_rejects_invalid_release_state(
    replacement,
    expected,
):
    lines = [
        line
        for line in SAMPLE.splitlines()
        if line
    ]

    if replacement.startswith("flags="):
        lines = [
            replacement
            if line.startswith("CodeDirectory ")
            else line
            for line in lines
        ]
    elif replacement.startswith("Signature="):
        lines = [
            replacement
            if line.startswith("Signature=")
            else line
            for line in lines
        ]
    elif replacement.startswith("TeamIdentifier="):
        lines = [
            replacement
            if line.startswith("TeamIdentifier=")
            else line
            for line in lines
        ]
    elif replacement.startswith("Identifier="):
        lines = [
            replacement
            if line.startswith("Identifier=")
            else line
            for line in lines
        ]

    details = MODULE.parse_codesign_details(
        "\n".join(lines)
    )

    with pytest.raises(
        MODULE.ReleaseError,
        match=expected,
    ):
        MODULE.validate_release_signature(
            details,
            team_id="TEAM123456",
            bundle_id="org.wamcoin.silentwallet",
        )


def test_release_signature_requires_timestamp():
    details = MODULE.parse_codesign_details(
        "\n".join(
            line
            for line in SAMPLE.splitlines()
            if not line.startswith("Timestamp=")
        )
    )

    with pytest.raises(
        MODULE.ReleaseError,
        match="SECURE_TIMESTAMP_MISSING",
    ):
        MODULE.validate_release_signature(
            details,
            team_id="TEAM123456",
            bundle_id="org.wamcoin.silentwallet",
        )
