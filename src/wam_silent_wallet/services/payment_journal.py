"""Crash-consistent local journal for signed payment material."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import stat


MAX_SIGNED_PSBT = 4 * 1024 * 1024

STATES = {
    "signed_material",
    "signed",
    "broadcasting",
    "uncertain",
    "broadcast",
}

TRANSITIONS = {
    "signed_material": {
        "signed_material",
        "signed",
    },
    "signed": {
        "signed",
        "broadcasting",
        "broadcast",
    },
    "broadcasting": {
        "broadcasting",
        "uncertain",
        "broadcast",
    },
    "uncertain": {
        "uncertain",
        "broadcast",
    },
    "broadcast": {
        "broadcast",
    },
}


class PaymentJournalService:
    DIRECTORY_NAME = ".payment-journal"

    def __init__(
        self,
        data_dir,
    ):
        self.data_dir = Path(
            data_dir
        )

        self.directory = (
            self.data_dir
            / self.DIRECTORY_NAME
        )

    @staticmethod
    def _validate_token(
        token,
    ):
        if (
            not isinstance(token, str)
            or not token
            or len(token) > 128
            or any(
                ord(ch) < 32
                for ch in token
            )
        ):
            raise ValueError(
                "PAYMENT_JOURNAL_TOKEN"
            )

    @staticmethod
    def _validate_manifest(
        manifest_digest,
    ):
        if (
            not isinstance(
                manifest_digest,
                str,
            )
            or len(manifest_digest) != 64
        ):
            raise ValueError(
                "PAYMENT_JOURNAL_MANIFEST"
            )

        try:
            bytes.fromhex(
                manifest_digest
            )
        except ValueError:
            raise ValueError(
                "PAYMENT_JOURNAL_MANIFEST"
            ) from None

    def _ensure_directory(
        self,
    ):
        if self.directory.is_symlink():
            raise RuntimeError(
                "PAYMENT_JOURNAL_UNSAFE"
            )

        self.directory.mkdir(
            parents=True,
            exist_ok=True,
            mode=0o700,
        )

        if (
            not self.directory.is_dir()
            or self.directory.is_symlink()
        ):
            raise RuntimeError(
                "PAYMENT_JOURNAL_UNSAFE"
            )

        if os.name == "posix":
            mode = (
                self.directory
                .stat()
                .st_mode
            )

            if mode & 0o077:
                raise RuntimeError(
                    "PAYMENT_JOURNAL_UNSAFE"
                )

    def _path(
        self,
        token,
    ):
        self._validate_token(
            token
        )

        name = (
            hashlib.sha256(
                token.encode(
                    "utf-8"
                )
            )
            .hexdigest()
            + ".json"
        )

        return (
            self.directory
            / name
        )

    @staticmethod
    def _encode(
        payload,
    ):
        return (
            json.dumps(
                payload,
                sort_keys=True,
                separators=(
                    ",",
                    ":",
                ),
            )
            .encode("utf-8")
            + bytes([10])
        )

    def _write_atomic(
        self,
        path,
        payload,
    ):
        self._ensure_directory()

        data = self._encode(
            payload
        )

        tmp = (
            self.directory
            / (
                "."
                + path.name
                + "."
                + secrets.token_hex(8)
                + ".tmp"
            )
        )

        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
        )

        flags |= getattr(
            os,
            "O_NOFOLLOW",
            0,
        )

        fd = None

        try:
            fd = os.open(
                tmp,
                flags,
                0o600,
            )

            with os.fdopen(
                fd,
                "wb",
            ) as stream:
                fd = None

                stream.write(
                    data
                )

                stream.flush()
                os.fsync(
                    stream.fileno()
                )

            os.replace(
                tmp,
                path,
            )

            if os.name == "posix":
                os.chmod(
                    path,
                    0o600,
                )

                directory_fd = os.open(
                    self.directory,
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

        except OSError as exc:
            if fd is not None:
                os.close(
                    fd
                )

            try:
                tmp.unlink(
                    missing_ok=True
                )
            except OSError:
                pass

            raise RuntimeError(
                "PAYMENT_JOURNAL_WRITE_FAILED"
            ) from exc

    def _load_payload(
        self,
        token,
    ):
        path = self._path(
            token
        )

        if not path.exists():
            return None

        try:
            st = path.lstat()

            if (
                stat.S_ISLNK(
                    st.st_mode
                )
                or not stat.S_ISREG(
                    st.st_mode
                )
            ):
                raise RuntimeError(
                    "PAYMENT_JOURNAL_CORRUPT_OR_UNSAFE"
                )

            if (
                os.name == "posix"
                and st.st_mode & 0o077
            ):
                raise RuntimeError(
                    "PAYMENT_JOURNAL_CORRUPT_OR_UNSAFE"
                )

            if (
                st.st_size <= 0
                or st.st_size
                > MAX_SIGNED_PSBT * 3
            ):
                raise RuntimeError(
                    "PAYMENT_JOURNAL_CORRUPT_OR_UNSAFE"
                )

            payload = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )

        except RuntimeError:
            raise

        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise RuntimeError(
                "PAYMENT_JOURNAL_CORRUPT_OR_UNSAFE"
            ) from exc

        expected = {
            "version",
            "token",
            "manifest_digest",
            "state",
            "psbt_hex",
            "psbt_sha256",
            "txid",
        }

        if (
            not isinstance(
                payload,
                dict,
            )
            or set(payload)
            != expected
            or payload[
                "version"
            ] != 1
            or payload[
                "token"
            ] != token
            or payload[
                "state"
            ] not in STATES
        ):
            raise RuntimeError(
                "PAYMENT_JOURNAL_CORRUPT_OR_UNSAFE"
            )

        try:
            self._validate_manifest(
                payload[
                    "manifest_digest"
                ]
            )

            signed_psbt = bytes.fromhex(
                payload[
                    "psbt_hex"
                ]
            )

        except (
            ValueError,
            TypeError,
        ) as exc:
            raise RuntimeError(
                "PAYMENT_JOURNAL_CORRUPT_OR_UNSAFE"
            ) from exc

        if (
            not signed_psbt
            or len(signed_psbt)
            > MAX_SIGNED_PSBT
        ):
            raise RuntimeError(
                "PAYMENT_JOURNAL_CORRUPT_OR_UNSAFE"
            )

        digest = hashlib.sha256(
            signed_psbt
        ).hexdigest()

        if digest != payload[
            "psbt_sha256"
        ]:
            raise RuntimeError(
                "PAYMENT_JOURNAL_CORRUPT_OR_UNSAFE"
            )

        txid = payload[
            "txid"
        ]

        if txid is not None:
            if (
                not isinstance(
                    txid,
                    str,
                )
                or len(txid) != 64
            ):
                raise RuntimeError(
                    "PAYMENT_JOURNAL_CORRUPT_OR_UNSAFE"
                )

            try:
                bytes.fromhex(
                    txid
                )
            except ValueError:
                raise RuntimeError(
                    "PAYMENT_JOURNAL_CORRUPT_OR_UNSAFE"
                ) from None

        return (
            payload,
            signed_psbt,
        )

    def record_signed(
        self,
        token,
        manifest_digest,
        signed_psbt,
    ):
        self._validate_token(
            token
        )

        self._validate_manifest(
            manifest_digest
        )

        if (
            not isinstance(
                signed_psbt,
                bytes,
            )
            or not signed_psbt
            or len(signed_psbt)
            > MAX_SIGNED_PSBT
        ):
            raise ValueError(
                "PAYMENT_JOURNAL_PSBT"
            )

        payload = {
            "version": 1,
            "token": token,
            "manifest_digest": (
                manifest_digest
            ),
            "state": (
                "signed_material"
            ),
            "psbt_hex": (
                signed_psbt.hex()
            ),
            "psbt_sha256": (
                hashlib.sha256(
                    signed_psbt
                ).hexdigest()
            ),
            "txid": None,
        }

        self._write_atomic(
            self._path(token),
            payload,
        )

    def transition(
        self,
        token,
        state,
        *,
        txid=None,
    ):
        if state not in STATES:
            raise ValueError(
                "PAYMENT_JOURNAL_STATE"
            )

        loaded = self._load_payload(
            token
        )

        if loaded is None:
            raise RuntimeError(
                "PAYMENT_JOURNAL_NOT_FOUND"
            )

        payload, _ = loaded

        current = payload[
            "state"
        ]

        if state not in TRANSITIONS[
            current
        ]:
            raise RuntimeError(
                "PAYMENT_JOURNAL_TRANSITION"
            )

        if txid is not None:
            if (
                not isinstance(
                    txid,
                    str,
                )
                or len(txid) != 64
            ):
                raise ValueError(
                    "PAYMENT_JOURNAL_TXID"
                )

            try:
                bytes.fromhex(
                    txid
                )
            except ValueError:
                raise ValueError(
                    "PAYMENT_JOURNAL_TXID"
                ) from None

            payload[
                "txid"
            ] = txid

        payload[
            "state"
        ] = state

        self._write_atomic(
            self._path(token),
            payload,
        )

    def rollback_broadcasting(
        self,
        token,
    ):
        loaded = self._load_payload(
            token
        )

        if loaded is None:
            raise RuntimeError(
                "PAYMENT_JOURNAL_NOT_FOUND"
            )

        payload, _ = loaded

        if payload[
            "state"
        ] != "broadcasting":
            raise RuntimeError(
                "PAYMENT_JOURNAL_TRANSITION"
            )

        payload[
            "state"
        ] = "signed"

        self._write_atomic(
            self._path(token),
            payload,
        )

    def load(
        self,
        token,
    ):
        loaded = self._load_payload(
            token
        )

        if loaded is None:
            return None

        payload, signed_psbt = (
            loaded
        )

        return {
            **payload,
            "signed_psbt": (
                signed_psbt
            ),
        }

    def unresolved(self):
        self._ensure_directory()

        result = []

        for path in sorted(
            self.directory.glob("*.json")
        ):
            try:
                st = path.lstat()

                if (
                    stat.S_ISLNK(st.st_mode)
                    or not stat.S_ISREG(st.st_mode)
                    or (
                        os.name == "posix"
                        and st.st_mode & 0o077
                    )
                    or st.st_size <= 0
                    or st.st_size > MAX_SIGNED_PSBT * 3
                ):
                    raise RuntimeError(
                        "PAYMENT_JOURNAL_CORRUPT_OR_UNSAFE"
                    )

                raw = json.loads(
                    path.read_text(
                        encoding="utf-8"
                    )
                )

                if not isinstance(raw, dict):
                    raise RuntimeError(
                        "PAYMENT_JOURNAL_CORRUPT_OR_UNSAFE"
                    )

                token = raw.get(
                    "token"
                )

                self._validate_token(
                    token
                )

                if self._path(token) != path:
                    raise RuntimeError(
                        "PAYMENT_JOURNAL_CORRUPT_OR_UNSAFE"
                    )

                loaded = self.load(
                    token
                )

            except RuntimeError:
                raise

            except Exception as exc:
                raise RuntimeError(
                    "PAYMENT_JOURNAL_CORRUPT_OR_UNSAFE"
                ) from exc

            if (
                loaded is not None
                and loaded["state"]
                != "broadcast"
            ):
                result.append(
                    loaded
                )

        return result

    def has_unresolved(self) -> bool:
        return bool(
            self.unresolved()
        )
