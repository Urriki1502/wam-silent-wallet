"""Wallet-layer hardening for encrypted spend-key material.

The WSP engine keeps its native encrypted envelope unchanged. The desktop
wallet adds one outer authenticated layer for keys.wsp so password guessing
must pass a stronger, versioned scrypt boundary before WSP key material is
reached. Legacy WSP envelopes remain readable and are migrated atomically
after a successful wallet/database identity check.
"""

from __future__ import annotations

import os
from pathlib import Path
import secrets
import stat

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from wam_sp.keystore import (
    Keyring,
    MAGIC as WSP_MAGIC,
)

from .filesystem_integrity import (
    harden_private_directory,
    harden_private_file,
)


KEY_KDF_MAGIC = b"WAMKDF1\x00"
SALT_BYTES = 16
NONCE_BYTES = 12
KEY_BYTES = 32

# Keep the established 32 MiB scrypt memory profile while increasing CPU
# work by 3x. This avoids platform-specific high-memory failures and raises
# the offline password-guessing cost without adding another dependency.
SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 3

MAX_KEY_ENVELOPE = 4 * 1024 * 1024
AAD = KEY_KDF_MAGIC + b"/keys.wsp/v1"


def _secret_bytes(secret) -> bytes:
    if isinstance(secret, str):
        value = secret.encode("utf-8")
    elif isinstance(secret, bytes):
        value = secret
    elif isinstance(secret, (bytearray, memoryview)):
        value = bytes(secret)
    else:
        raise ValueError("PASSPHRASE_REQUIRED")

    if not 12 <= len(value) <= 1024:
        raise ValueError("PASSPHRASE_LENGTH")

    return value


def _derive(secret, salt: bytes) -> bytearray:
    if (
        not isinstance(salt, bytes)
        or len(salt) != SALT_BYTES
    ):
        raise ValueError("WALLET_KDF_SALT")

    derived = Scrypt(
        salt=salt,
        length=KEY_BYTES,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
    ).derive(
        _secret_bytes(secret)
    )

    return bytearray(derived)


def _wipe(value: bytearray):
    for index in range(len(value)):
        value[index] = 0


def protect_keyring(
    ring: Keyring,
    secret,
) -> bytes:
    if not isinstance(ring, Keyring):
        raise ValueError("WALLET_KEYRING_REQUIRED")

    salt = secrets.token_bytes(
        SALT_BYTES
    )
    nonce = secrets.token_bytes(
        NONCE_BYTES
    )
    key = _derive(
        secret,
        salt,
    )

    try:
        key_bytes = bytes(key)

        inner = ring.backup(
            key_bytes
        )

        ciphertext = AESGCM(
            key_bytes
        ).encrypt(
            nonce,
            inner,
            AAD,
        )

        envelope = (
            KEY_KDF_MAGIC
            + salt
            + nonce
            + ciphertext
        )

        if len(envelope) > MAX_KEY_ENVELOPE:
            raise ValueError(
                "WALLET_KEYS_LIMIT"
            )

        return envelope

    finally:
        _wipe(key)


def restore_keyring(
    envelope: bytes,
    secret,
) -> tuple[Keyring, bool]:
    """Return (keyring, legacy_source)."""

    if (
        not isinstance(envelope, bytes)
        or len(envelope) < 52
        or len(envelope) > MAX_KEY_ENVELOPE
    ):
        raise ValueError(
            "WALLET_KEYS_FORMAT"
        )

    if envelope[:8] == WSP_MAGIC:
        return (
            Keyring.restore(
                envelope,
                _secret_bytes(secret),
            ),
            True,
        )

    if envelope[:8] != KEY_KDF_MAGIC:
        raise ValueError(
            "WALLET_KEYS_FORMAT"
        )

    minimum = (
        8
        + SALT_BYTES
        + NONCE_BYTES
        + 16
    )

    if len(envelope) <= minimum:
        raise ValueError(
            "WALLET_KEYS_FORMAT"
        )

    salt_start = 8
    nonce_start = (
        salt_start
        + SALT_BYTES
    )
    ciphertext_start = (
        nonce_start
        + NONCE_BYTES
    )

    salt = envelope[
        salt_start:nonce_start
    ]
    nonce = envelope[
        nonce_start:ciphertext_start
    ]
    ciphertext = envelope[
        ciphertext_start:
    ]

    key = _derive(
        secret,
        salt,
    )

    try:
        key_bytes = bytes(key)

        try:
            inner = AESGCM(
                key_bytes
            ).decrypt(
                nonce,
                ciphertext,
                AAD,
            )
        except InvalidTag:
            raise ValueError(
                "WALLET_KEYS_AUTHENTICATION"
            ) from None

        if (
            len(inner) < 52
            or inner[:8] != WSP_MAGIC
        ):
            raise ValueError(
                "WALLET_KEYS_INNER_FORMAT"
            )

        try:
            ring = Keyring.restore(
                inner,
                key_bytes,
            )
        except ValueError:
            raise ValueError(
                "WALLET_KEYS_INNER_FORMAT"
            ) from None

        return ring, False

    finally:
        _wipe(key)


def _write_new_private(
    path: Path,
    data: bytes,
):
    path = Path(path)

    if (
        not isinstance(data, bytes)
        or data[:8] != KEY_KDF_MAGIC
        or len(data) > MAX_KEY_ENVELOPE
    ):
        raise ValueError(
            "WALLET_KEYS_FORMAT"
        )

    harden_private_directory(
        path.parent,
        create=False,
        code="WALLET_KEYS_DIRECTORY_UNSAFE",
    )

    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(
            os,
            "O_NOFOLLOW",
            0,
        )
    )

    descriptor = None

    try:
        descriptor = os.open(
            path,
            flags,
            0o600,
        )

        metadata = os.fstat(
            descriptor
        )

        if (
            not stat.S_ISREG(
                metadata.st_mode
            )
            or getattr(
                metadata,
                "st_nlink",
                1,
            ) != 1
        ):
            raise RuntimeError(
                "WALLET_KEYS_UNSAFE"
            )

        with os.fdopen(
            descriptor,
            "wb",
        ) as handle:
            descriptor = None
            handle.write(
                data
            )
            handle.flush()
            os.fsync(
                handle.fileno()
            )

    finally:
        if descriptor is not None:
            os.close(
                descriptor
            )


def atomic_replace_keyring(
    path: Path,
    ring: Keyring,
    secret,
):
    path = Path(path)

    protected = protect_keyring(
        ring,
        secret,
    )

    temporary = path.with_name(
        ".keys.wsp.next"
    )

    if temporary.is_symlink():
        raise RuntimeError(
            "WALLET_KEYS_UNSAFE"
        )

    temporary.unlink(
        missing_ok=True
    )

    try:
        _write_new_private(
            temporary,
            protected,
        )

        os.replace(
            temporary,
            path,
        )

        harden_private_file(
            path,
            required=True,
            code="WALLET_KEYS_UNSAFE",
        )

        if os.name == "posix":
            directory_fd = os.open(
                path.parent,
                os.O_RDONLY,
            )

            try:
                os.fsync(
                    directory_fd
                )
            finally:
                os.close(
                    directory_fd
                )

    finally:
        temporary.unlink(
            missing_ok=True
        )
