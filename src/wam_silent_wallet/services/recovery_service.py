"""Hardened active-wallet recovery boundary.

Recovery is staged completely outside the active wallet first.

Security properties:
- authenticated bundle is restored into a private staging directory;
- active wallet files are untouched until staging validation succeeds;
- draft reservations are discarded on recovery;
- signed/uncertain/broadcast/manual reservations remain locked;
- restored key material is re-opened before activation;
- wallet.db + keys.wsp + recovery-pending marker are activated together;
- partial activation attempts roll back to the previous wallet;
- recovered wallets remain spend-blocked until chain reconciliation completes.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
import uuid

from wam_sp.api import SilentWallet
from wam_sp.backup import restore as restore_recovery
from wam_sp.keystore import (
    Keyring,
    load_private,
    save_private,
)

from .filesystem_integrity import (
    harden_private_directory,
    harden_private_file,
)


class RecoveryService:
    PENDING_VERSION = 1
    DB_PENDING_KEY = "recovery_pending_v1"

    ACTIVATION_JOURNAL_VERSION = 1
    ACTIVATION_JOURNAL_NAME = (
        ".recovery-activation.json"
    )

    def __init__(
        self,
        data_dir: Path,
        db_path: Path,
        keys_path: Path,
    ):
        self.data_dir = Path(data_dir)
        self.db_path = Path(db_path)
        self.keys_path = Path(keys_path)

        self.pending_path = (
            self.data_dir
            / "recovery-pending.json"
        )

        self.activation_journal_path = (
            self.data_dir
            / self.ACTIVATION_JOURNAL_NAME
        )

    # ----------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------

    @staticmethod
    def _password_bytes(secret) -> bytes:
        if isinstance(secret, str):
            value = secret.encode("utf-8")
        elif isinstance(secret, bytes):
            value = secret
        elif isinstance(
            secret,
            (bytearray, memoryview),
        ):
            value = bytes(secret)
        else:
            raise ValueError(
                "PASSPHRASE_REQUIRED"
            )

        if not value:
            raise ValueError(
                "PASSPHRASE_REQUIRED"
            )

        return value

    @staticmethod
    def _private_dir(
        path: Path,
    ):
        harden_private_directory(
            path,
            create=True,
            code="RECOVERY_DIRECTORY_UNSAFE",
        )

    @staticmethod
    def _fsync_dir(
        path: Path,
    ):
        try:
            descriptor = os.open(
                path,
                os.O_RDONLY,
            )
        except OSError:
            return

        try:
            os.fsync(
                descriptor
            )
        except OSError:
            pass
        finally:
            os.close(
                descriptor
            )

    @staticmethod
    def _write_private_json(
        path: Path,
        payload: dict,
    ):
        raw = (
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")

        descriptor = os.open(
            path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(
                os,
                "O_NOFOLLOW",
                0,
            ),
            0o600,
        )

        with os.fdopen(
            descriptor,
            "wb",
        ) as handle:
            handle.write(
                raw
            )

            handle.flush()

            os.fsync(
                handle.fileno()
            )

    @staticmethod
    def _atomic_json_replace(
        path: Path,
        payload: dict,
    ):
        raw = (
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")

        temporary = (
            path.parent
            / (
                path.name
                + ".tmp-"
                + uuid.uuid4().hex
            )
        )

        descriptor = os.open(
            temporary,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(
                os,
                "O_NOFOLLOW",
                0,
            ),
            0o600,
        )

        try:
            with os.fdopen(
                descriptor,
                "wb",
            ) as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(
                    handle.fileno()
                )

            os.replace(
                temporary,
                path,
            )

        finally:
            temporary.unlink(
                missing_ok=True
            )

    def _write_activation_journal(
        self,
        payload: dict,
    ):
        self._atomic_json_replace(
            self.activation_journal_path,
            payload,
        )

        self._fsync_dir(
            self.data_dir
        )

    @staticmethod
    def _valid_rollback_name(
        value,
    ) -> bool:
        prefix = ".recovery-rollback-"

        if (
            not isinstance(
                value,
                str,
            )
            or Path(value).name
            != value
            or not value.startswith(
                prefix
            )
        ):
            return False

        suffix = value[
            len(prefix):
        ]

        return (
            len(suffix) == 32
            and all(
                ch in "0123456789abcdef"
                for ch in suffix
            )
        )

    def _load_activation_journal(
        self,
    ) -> dict | None:
        path = (
            self.activation_journal_path
        )

        if path.is_symlink():
            raise RuntimeError(
                "RECOVERY_ACTIVATION_JOURNAL_UNSAFE"
            )

        if not path.exists():
            return None

        try:
            harden_private_file(
                path,
                required=True,
                code="RECOVERY_ACTIVATION_JOURNAL_UNSAFE",
            )

            data = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )
        except RuntimeError:
            raise

        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
        ):
            raise RuntimeError(
                "RECOVERY_ACTIVATION_JOURNAL_INVALID"
            ) from None

        if (
            not isinstance(data, dict)
            or data.get("version")
            != self.ACTIVATION_JOURNAL_VERSION
            or data.get("phase")
            not in (
                "prepared",
                "old-moved",
                "new-installed",
                "verified",
            )
            or not self._valid_rollback_name(
                data.get(
                    "rollback_dir"
                )
            )
            or not isinstance(
                data.get("original_presence"),
                dict,
            )
        ):
            raise RuntimeError(
                "RECOVERY_ACTIVATION_JOURNAL_INVALID"
            )

        return data

    def recover_interrupted_activation(
        self,
    ) -> str | None:
        journal = (
            self._load_activation_journal()
        )

        if journal is None:
            return None

        rollback_dir = (
            self.data_dir
            / journal["rollback_dir"]
        )

        harden_private_directory(
            rollback_dir,
            create=False,
            code="RECOVERY_ROLLBACK_UNSAFE",
        )

        # If verification completed before the crash, the new
        # active wallet is authoritative. Only cleanup remains.
        if journal["phase"] == "verified":
            shutil.rmtree(
                rollback_dir,
                ignore_errors=True,
            )

            self.activation_journal_path.unlink(
                missing_ok=True
            )

            self._fsync_dir(
                self.data_dir
            )

            return "finalized"

        active_files = {
            "wallet.db": self.db_path,
            "keys.wsp": self.keys_path,
            "recovery-pending.json": (
                self.pending_path
            ),
        }

        for active in active_files.values():
            if active.is_symlink():
                raise RuntimeError(
                    "RECOVERY_ACTIVE_FILE_UNSAFE"
                )

        original_presence = (
            journal["original_presence"]
        )

        try:
            for name, active in active_files.items():
                backup = (
                    rollback_dir
                    / name
                )

                # If the original file was already moved into the
                # rollback directory, restore it and discard any
                # partially installed replacement.
                if backup.exists():
                    active.unlink(
                        missing_ok=True
                    )

                    os.replace(
                        backup,
                        active,
                    )

                    continue

                # No original existed before activation. A file
                # appearing now can only be part of the partial
                # recovered set and must be removed.
                if not bool(
                    original_presence.get(
                        name,
                        False,
                    )
                ):
                    active.unlink(
                        missing_ok=True
                    )

                # If the original was present but no rollback copy
                # exists, the atomic move had not completed. Leave
                # the active original in place.

            shutil.rmtree(
                rollback_dir,
                ignore_errors=True,
            )

            self.activation_journal_path.unlink(
                missing_ok=True
            )

            self._fsync_dir(
                self.data_dir
            )

        except OSError:
            raise RuntimeError(
                "RECOVERY_STARTUP_REPAIR_FAILED"
            ) from None

        return "rolled-back"

    # ----------------------------------------------------------
    # Recovery-pending state
    # ----------------------------------------------------------

    @classmethod
    def _validate_marker(
        cls,
        data,
    ) -> dict:
        if (
            not isinstance(data, dict)
            or data.get("version")
            != cls.PENDING_VERSION
            or not isinstance(
                data.get("sha256"),
                str,
            )
            or len(
                data["sha256"]
            )
            != 64
            or not isinstance(
                data.get("base_address"),
                str,
            )
            or not data["base_address"]
            or data.get("reason")
            != "chain-reconciliation-required"
        ):
            raise ValueError(
                "RECOVERY_PENDING_STATE"
            )

        return data

    def _db_pending_info(
        self,
    ) -> dict | None:
        if not self.db_path.is_file():
            return None

        try:
            connection = sqlite3.connect(
                f"file:{self.db_path}?mode=ro",
                uri=True,
            )

            try:
                row = connection.execute(
                    """
                    SELECT value
                    FROM meta
                    WHERE key=?
                    """,
                    (
                        self.DB_PENDING_KEY,
                    ),
                ).fetchone()

            finally:
                connection.close()

        except sqlite3.DatabaseError:
            raise ValueError(
                "RECOVERY_PENDING_STATE"
            ) from None

        if row is None:
            return None

        try:
            data = json.loads(
                row[0]
            )
        except (
            TypeError,
            json.JSONDecodeError,
        ):
            raise ValueError(
                "RECOVERY_PENDING_STATE"
            ) from None

        return self._validate_marker(
            data
        )

    def _file_pending_info(
        self,
    ) -> dict | None:
        if self.pending_path.is_symlink():
            raise RuntimeError(
                "RECOVERY_PENDING_FILE_UNSAFE"
            )

        if not self.pending_path.exists():
            return None

        try:
            harden_private_file(
                self.pending_path,
                required=True,
                code="RECOVERY_PENDING_FILE_UNSAFE",
            )

            data = json.loads(
                self.pending_path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
        ):
            raise ValueError(
                "RECOVERY_PENDING_STATE"
            ) from None

        return self._validate_marker(
            data
        )

    def pending(
        self,
    ) -> bool:
        return (
            self._db_pending_info()
            is not None
            or self._file_pending_info()
            is not None
        )

    def pending_info(
        self,
    ) -> dict | None:
        database = (
            self._db_pending_info()
        )

        sidecar = (
            self._file_pending_info()
        )

        if (
            database is not None
            and sidecar is not None
            and database != sidecar
        ):
            raise ValueError(
                "RECOVERY_PENDING_STATE"
            )

        return (
            database
            if database is not None
            else sidecar
        )

    # ----------------------------------------------------------
    # Activation
    # ----------------------------------------------------------

    def _activate(
        self,
        *,
        staged_db: Path,
        staged_keys: Path,
        staged_pending: Path,
        password: bytes,
        expected_address: str,
    ):
        db_exists = (
            self.db_path.exists()
        )

        keys_exists = (
            self.keys_path.exists()
        )

        if db_exists != keys_exists:
            raise ValueError(
                "RECOVERY_ACTIVE_WALLET_INCOMPLETE"
            )

        if (
            self.activation_journal_path.exists()
            or self.activation_journal_path.is_symlink()
        ):
            raise ValueError(
                "RECOVERY_ACTIVATION_ALREADY_PENDING"
            )

        rollback_dir = (
            self.data_dir
            / (
                ".recovery-rollback-"
                + uuid.uuid4().hex
            )
        )

        self._private_dir(
            rollback_dir
        )

        active_files = {
            "wallet.db": self.db_path,
            "keys.wsp": self.keys_path,
            "recovery-pending.json": (
                self.pending_path
            ),
        }

        original_presence = {
            name: active.exists()
            for name, active
            in active_files.items()
        }

        journal = {
            "version": (
                self.ACTIVATION_JOURNAL_VERSION
            ),
            "phase": "prepared",
            "rollback_dir": (
                rollback_dir.name
            ),
            "original_presence": (
                original_presence
            ),
        }

        self._write_activation_journal(
            journal
        )

        old_files = []
        installed = []

        new_files = [
            (
                staged_db,
                self.db_path,
            ),
            (
                staged_keys,
                self.keys_path,
            ),
            (
                staged_pending,
                self.pending_path,
            ),
        ]

        try:
            # Move the current active set into durable rollback
            # storage. os.replace() gives atomic per-file moves.
            for name, active in active_files.items():
                if not active.exists():
                    continue

                rollback = (
                    rollback_dir
                    / name
                )

                os.replace(
                    active,
                    rollback,
                )

                old_files.append(
                    (
                        rollback,
                        active,
                    )
                )

            self._fsync_dir(
                self.data_dir
            )

            journal["phase"] = (
                "old-moved"
            )

            self._write_activation_journal(
                journal
            )

            # Install the staged recovered set.
            for staged, active in new_files:
                os.replace(
                    staged,
                    active,
                )

                installed.append(
                    active
                )

            self._fsync_dir(
                self.data_dir
            )

            journal["phase"] = (
                "new-installed"
            )

            self._write_activation_journal(
                journal
            )

            # Re-open ACTIVE files after replacement. This is the
            # final cryptographic + identity verification boundary.
            encrypted = load_private(
                self.keys_path
            )

            ring = Keyring.restore(
                encrypted,
                password,
            )

            wallet = None

            try:
                wallet = SilentWallet(
                    self.db_path,
                    ring.accounts(),
                )

                actual_address = (
                    wallet
                    .get_silent_address()
                )

                if (
                    actual_address
                    != expected_address
                ):
                    raise ValueError(
                        "RECOVERY_IDENTITY_MISMATCH"
                    )

            finally:
                if wallet is not None:
                    wallet.close()

                ring.close()

            # Once VERIFIED is durable, startup recovery must keep
            # the recovered wallet and only finish cleanup.
            journal["phase"] = "verified"

            self._write_activation_journal(
                journal
            )

        except Exception:
            rollback_failed = False

            for active in installed:
                try:
                    active.unlink(
                        missing_ok=True
                    )
                except OSError:
                    rollback_failed = True

            for rollback, active in reversed(
                old_files
            ):
                try:
                    os.replace(
                        rollback,
                        active,
                    )
                except OSError:
                    rollback_failed = True

            self._fsync_dir(
                self.data_dir
            )

            if rollback_failed:
                # Preserve both journal + rollback directory so the
                # next application start can attempt self-healing.
                raise RuntimeError(
                    "RECOVERY_ROLLBACK_FAILED"
                ) from None

            shutil.rmtree(
                rollback_dir,
                ignore_errors=True,
            )

            self.activation_journal_path.unlink(
                missing_ok=True
            )

            self._fsync_dir(
                self.data_dir
            )

            raise ValueError(
                "RECOVERY_ACTIVATION_FAILED"
            ) from None

        # Normal successful cleanup. If the process dies after
        # VERIFIED but before this cleanup, startup self-healing
        # finalizes the same state safely.
        shutil.rmtree(
            rollback_dir,
            ignore_errors=True,
        )

        self.activation_journal_path.unlink(
            missing_ok=True
        )

        self._fsync_dir(
            self.data_dir
        )

    # ----------------------------------------------------------
    # Chain reconciliation
    # ----------------------------------------------------------

    def reconcile(
        self,
        wallet,
        chain,
    ) -> dict:
        pending = self.pending_info()

        if pending is None:
            raise ValueError(
                "RECOVERY_NOT_PENDING"
            )

        if (
            wallet.get_silent_address()
            != pending["base_address"]
        ):
            raise ValueError(
                "RECOVERY_IDENTITY_MISMATCH"
            )

        try:
            metrics = wallet.scan(
                chain,
                mempool=True,
            )

            wallet.scanner.assert_current()

            if not wallet.scanner.mempool_ready:
                raise ValueError(
                    "MEMPOOL_NOT_CURRENT"
                )

        except Exception:
            # Never remove the recovery spend gate unless both
            # chain and mempool snapshots are current.
            raise ValueError(
                "RECOVERY_RECONCILIATION_FAILED"
            ) from None

        scanner = wallet.scanner
        db = scanner.store.db

        resolved_confirmed = 0
        dropped_missing = 0
        dropped_draft = 0
        manual_locked = 0
        uncertain_locked = 0
        mempool_locked = 0

        with scanner.store.transaction():
            rows = list(
                db.execute(
                    """
                    SELECT
                        txid,
                        vout,
                        token,
                        state,
                        created
                    FROM reservations
                    ORDER BY txid,vout
                    """
                )
            )

            for row in rows:
                txid = row["txid"]
                vout = row["vout"]
                state = row["state"]

                coin = db.execute(
                    """
                    SELECT spent
                    FROM coins
                    WHERE txid=?
                      AND vout=?
                    """,
                    (
                        txid,
                        vout,
                    ),
                ).fetchone()

                mempool = db.execute(
                    """
                    SELECT spending
                    FROM mempool_spends
                    WHERE txid=?
                      AND vout=?
                    """,
                    (
                        txid,
                        vout,
                    ),
                ).fetchone()

                # The recovered outpoint no longer belongs to
                # this wallet on the verified chain.
                if coin is None:
                    db.execute(
                        """
                        DELETE FROM reservations
                        WHERE txid=?
                          AND vout=?
                        """,
                        (
                            txid,
                            vout,
                        ),
                    )

                    dropped_missing += 1
                    continue

                # Confirmed chain spend resolves the old lock.
                if coin["spent"] is not None:
                    db.execute(
                        """
                        DELETE FROM reservations
                        WHERE txid=?
                          AND vout=?
                        """,
                        (
                            txid,
                            vout,
                        ),
                    )

                    resolved_confirmed += 1
                    continue

                # Defensive cleanup. Restore already removes
                # drafts before activation.
                if state == "draft":
                    db.execute(
                        """
                        DELETE FROM reservations
                        WHERE txid=?
                          AND vout=?
                        """,
                        (
                            txid,
                            vout,
                        ),
                    )

                    dropped_draft += 1
                    continue

                if state == "manual":
                    manual_locked += 1
                    continue

                # A signed/broadcast reservation whose input is
                # still unspent cannot safely be auto-released:
                # a valid signed transaction may still exist
                # outside this process. Normalize it to
                # 'uncertain' until explicitly resolved by chain.
                db.execute(
                    """
                    UPDATE reservations
                    SET state='uncertain'
                    WHERE txid=?
                      AND vout=?
                    """,
                    (
                        txid,
                        vout,
                    ),
                )

                uncertain_locked += 1

                if mempool is not None:
                    mempool_locked += 1

            scanner.store.validate()

            # DB gate is cleared only after successful verified
            # chain + mempool reconciliation and reservation
            # normalization.
            db.execute(
                """
                DELETE FROM meta
                WHERE key=?
                """,
                (
                    self.DB_PENDING_KEY,
                ),
            )

        # DB commit happened first. If sidecar removal fails,
        # the remaining file keeps spending blocked.
        try:
            self.pending_path.unlink(
                missing_ok=True
            )
        except OSError:
            raise ValueError(
                "RECOVERY_PENDING_CLEAR_FAILED"
            ) from None

        self._fsync_dir(
            self.data_dir
        )

        return {
            "sha256": pending["sha256"],
            "base_address": (
                pending["base_address"]
            ),
            "scan_blocks": getattr(
                metrics,
                "blocks",
                0,
            ),
            "scan_transactions": getattr(
                metrics,
                "transactions",
                0,
            ),
            "scan_rollback": getattr(
                metrics,
                "rollback",
                0,
            ),
            "resolved_confirmed": (
                resolved_confirmed
            ),
            "dropped_missing": (
                dropped_missing
            ),
            "dropped_draft": (
                dropped_draft
            ),
            "manual_locked": (
                manual_locked
            ),
            "uncertain_locked": (
                uncertain_locked
            ),
            "mempool_locked": (
                mempool_locked
            ),
            "reconciliation_required": False,
        }

    # ----------------------------------------------------------
    # Public restore
    # ----------------------------------------------------------

    def restore(
        self,
        passphrase,
        backup_path: str,
    ) -> dict:
        path = Path(
            backup_path
        ).expanduser()

        if not path.is_file():
            raise ValueError(
                "RECOVERY_FILE_NOT_FOUND"
            )

        password = (
            self._password_bytes(
                passphrase
            )
        )

        try:
            envelope = load_private(
                path
            )
        except Exception:
            raise ValueError(
                "RECOVERY_FILE_INVALID"
            ) from None

        digest = hashlib.sha256(
            envelope
        ).hexdigest()

        self._private_dir(
            self.data_dir
        )

        temp_root = Path(
            tempfile.mkdtemp(
                prefix=".recovery-stage-",
                dir=self.data_dir,
            )
        )

        try:
            try:
                os.chmod(
                    temp_root,
                    0o700,
                )
            except OSError:
                pass

            staged_db = (
                temp_root
                / "wallet.db"
            )

            staged_keys = (
                temp_root
                / "keys.wsp"
            )

            staged_pending = (
                temp_root
                / "recovery-pending.json"
            )

            try:
                ring, scanner = (
                    restore_recovery(
                        envelope,
                        password,
                        staged_db,
                    )
                )
            except Exception:
                raise ValueError(
                    "RECOVERY_RESTORE_FAILED"
                ) from None

            try:
                accounts = (
                    ring.accounts()
                )

                if not accounts:
                    raise ValueError(
                        "RECOVERY_NO_ACCOUNTS"
                    )

                base_address = (
                    max(
                        accounts,
                        key=lambda item: (
                            item.epoch
                        ),
                    )
                    .payment_code()
                )

                db = (
                    scanner.store.db
                )

                marker = {
                    "version": (
                        self.PENDING_VERSION
                    ),
                    "sha256": digest,
                    "base_address": (
                        base_address
                    ),
                    "created": int(
                        time.time()
                    ),
                    "reason": (
                        "chain-reconciliation-required"
                    ),
                }

                marker_json = json.dumps(
                    marker,
                    sort_keys=True,
                    separators=(",", ":"),
                )

                with (
                    scanner.store.transaction()
                ):
                    drafts = db.execute(
                        """
                        SELECT COUNT(*)
                        FROM reservations
                        WHERE state='draft'
                        """
                    ).fetchone()[0]

                    # Unsigned drafts are disposable after
                    # recovery.  They have no irreversible
                    # signature attached to them.
                    db.execute(
                        """
                        DELETE FROM reservations
                        WHERE state='draft'
                        """
                    )

                    protected = db.execute(
                        """
                        SELECT COUNT(*)
                        FROM reservations
                        WHERE state IN (
                            'signed',
                            'uncertain',
                            'broadcast',
                            'manual'
                        )
                        """
                    ).fetchone()[0]

                    # Persist the spend gate inside the restored
                    # database as well as in the sidecar marker.
                    db.execute(
                        """
                        INSERT OR REPLACE
                        INTO meta(key,value)
                        VALUES(?,?)
                        """,
                        (
                            self.DB_PENDING_KEY,
                            marker_json,
                        ),
                    )

                    scanner.store.validate()

                encrypted_keys = (
                    ring.backup(
                        password
                    )
                )

                save_private(
                    staged_keys,
                    encrypted_keys,
                )

                self._write_private_json(
                    staged_pending,
                    marker,
                )

                labels = sum(
                    len(account.labels)
                    for account
                    in accounts
                )

            finally:
                scanner.close()
                ring.close()

            # Verify staged keys + DB independently before touching
            # the current wallet.
            verify_encrypted = (
                load_private(
                    staged_keys
                )
            )

            verify_ring = (
                Keyring.restore(
                    verify_encrypted,
                    password,
                )
            )

            verify_wallet = None

            try:
                verify_wallet = (
                    SilentWallet(
                        staged_db,
                        verify_ring.accounts(),
                    )
                )

                if (
                    verify_wallet
                    .get_silent_address()
                    != base_address
                ):
                    raise ValueError(
                        "RECOVERY_IDENTITY_MISMATCH"
                    )

            finally:
                if verify_wallet is not None:
                    verify_wallet.close()

                verify_ring.close()

            self._activate(
                staged_db=staged_db,
                staged_keys=staged_keys,
                staged_pending=staged_pending,
                password=password,
                expected_address=(
                    base_address
                ),
            )

            return {
                "sha256": digest,
                "accounts": len(
                    accounts
                ),
                "labels": labels,
                "base_address": (
                    base_address
                ),
                "draft_reservations_dropped": (
                    drafts
                ),
                "protected_reservations": (
                    protected
                ),
                "reconciliation_required": True,
            }

        finally:
            shutil.rmtree(
                temp_root,
                ignore_errors=True,
            )
