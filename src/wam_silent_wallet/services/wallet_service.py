import os
import sqlite3
import hashlib
import json
import shutil
import tempfile
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TypeAlias

from .recovery_service import RecoveryService
from .scanner_snapshot import build_scanner_snapshot
from .payment_journal import PaymentJournalService
from .payment_reconciliation import PaymentReconciliationService
from .filesystem_integrity import (
    harden_private_directory,
    harden_private_file,
)
from .key_protection import (
    KEY_KDF_MAGIC,
    atomic_replace_keyring,
    restore_keyring,
)

from wam_sp.api import SilentWallet
from wam_sp.keystore import MAGIC, Keyring, load_private, save_private
from wam_sp.backup import (
    create as create_recovery,
    restore as restore_recovery,
)


SecretMaterial: TypeAlias = str | bytes | bytearray | memoryview

ATOMS_PER_WAM = 100_000_000


class WalletService:
    @staticmethod
    def resolve_data_dir(
        data_dir: Path | None = None,
    ) -> Path:
        if data_dir is not None:
            return Path(
                data_dir
            ).expanduser()

        override = os.environ.get(
            "WAM_SILENT_WALLET_DATA_DIR"
        )

        if override:
            return Path(
                override
            ).expanduser()

        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "WAM Silent Wallet Demo"
        )

    def __init__(
        self,
        data_dir: Path | None = None,
    ):
        self.data_dir = (
            self.resolve_data_dir(
                data_dir
            )
        )

        if self.data_dir.is_symlink():
            raise RuntimeError(
                "WALLET_DATA_DIR_SYMLINK"
            )

        harden_private_directory(
            self.data_dir,
            create=True,
            code="WALLET_DATA_DIR_UNSAFE",
        )

        self.db_path = (
            self.data_dir
            / "wallet.db"
        )

        self.keys_path = (
            self.data_dir
            / "keys.wsp"
        )

        self.recovery = RecoveryService(
            self.data_dir,
            self.db_path,
            self.keys_path,
        )

        self.payment_journal = (
            PaymentJournalService(
                self.data_dir
            )
        )

        self.payment_reconciliation = (
            PaymentReconciliationService(
                self.payment_journal
            )
        )

        # Repair or finalize any recovery activation interrupted
        # by process termination, power loss, or OS crash.
        self.recovery.recover_interrupted_activation()

        self._validate_startup_fileset()

    def _validate_startup_fileset(
        self,
    ):
        if self.data_dir.is_symlink():
            raise RuntimeError(
                "WALLET_DATA_DIR_SYMLINK"
            )

        if (
            self.data_dir.exists()
            and not self.data_dir.is_dir()
        ):
            raise RuntimeError(
                "WALLET_DATA_DIR_INVALID"
            )

        harden_private_directory(
            self.data_dir,
            create=True,
            code="WALLET_DATA_DIR_UNSAFE",
        )

        for path in (
            self.db_path,
            self.keys_path,
        ):
            if path.is_symlink():
                raise RuntimeError(
                    "WALLET_FILESET_SYMLINK"
                )

        db_exists = (
            self.db_path.exists()
        )

        keys_exist = (
            self.keys_path.exists()
        )

        if db_exists != keys_exist:
            raise RuntimeError(
                "WALLET_FILESET_INCOMPLETE"
            )

        if not db_exists:
            return

        if (
            not self.db_path.is_file()
            or not self.keys_path.is_file()
        ):
            raise RuntimeError(
                "WALLET_FILESET_NOT_REGULAR"
            )

        harden_private_file(
            self.db_path,
            required=True,
            code="WALLET_DATABASE_UNSAFE",
        )


    def _validate_database_preflight(
        self,
    ):
        try:
            size = self.db_path.stat().st_size

            if size < 16:
                raise RuntimeError(
                    "WALLET_DATABASE_CORRUPT"
                )

            with self.db_path.open(
                "rb"
            ) as handle:
                header = handle.read(
                    16
                )

            if header != (b"SQLite format 3" + bytes([0])):
                raise RuntimeError(
                    "WALLET_DATABASE_CORRUPT"
                )

            uri = (
                "file:"
                + self.db_path.as_posix()
                + "?mode=ro"
            )

            db = sqlite3.connect(
                uri,
                uri=True,
                timeout=1,
            )

            try:
                rows = db.execute(
                    "PRAGMA quick_check"
                ).fetchall()

            finally:
                db.close()

            if rows != [("ok",)]:
                raise RuntimeError(
                    "WALLET_DATABASE_CORRUPT"
                )

        except RuntimeError:
            raise

        except (
            OSError,
            sqlite3.DatabaseError,
        ) as exc:
            raise RuntimeError(
                "WALLET_DATABASE_CORRUPT"
            ) from exc

    def _validate_keys_preflight(
        self,
    ):
        try:
            envelope = load_private(
                self.keys_path
            )

        except (
            OSError,
            ValueError,
        ) as exc:
            raise RuntimeError(
                "WALLET_KEYS_CORRUPT_OR_UNSAFE"
            ) from exc

        if (
            len(envelope) < 52
            or envelope[:8]
            not in {
                MAGIC,
                KEY_KDF_MAGIC,
            }
        ):
            raise RuntimeError(
                "WALLET_KEYS_CORRUPT"
            )

    def exists(self) -> bool:
        return (
            self.db_path.exists()
            and self.keys_path.exists()
        )

    @staticmethod
    def _password_bytes(secret) -> bytes:
        if isinstance(secret, str):
            value = secret.encode("utf-8")
        elif isinstance(secret, bytes):
            value = secret
        elif isinstance(secret, (bytearray, memoryview)):
            value = bytes(secret)
        else:
            raise ValueError("PASSPHRASE_REQUIRED")

        if not value:
            raise ValueError("PASSPHRASE_REQUIRED")

        return value

    def _database_wallet_identity(
        self,
    ) -> dict:
        uri = (
            "file:"
            + self.db_path.as_posix()
            + "?mode=ro"
        )

        try:
            db = sqlite3.connect(
                uri,
                uri=True,
                timeout=1,
            )

            try:
                row = db.execute(
                    """
                    SELECT value
                    FROM meta
                    WHERE key='identity'
                    """
                ).fetchone()
            finally:
                db.close()

            if row is None:
                raise ValueError

            value = json.loads(
                row[0]
            )

            if (
                not isinstance(
                    value,
                    dict,
                )
                or value.get(
                    "version"
                ) != 2
                or not isinstance(
                    value.get(
                        "accounts"
                    ),
                    list,
                )
            ):
                raise ValueError

            return value

        except (
            OSError,
            sqlite3.DatabaseError,
            ValueError,
            TypeError,
        ) as exc:
            raise RuntimeError(
                "WALLET_IDENTITY_CORRUPT"
            ) from exc

    def _reconcile_keyring_metadata(
        self,
        ring: Keyring,
    ) -> bool:
        stored = (
            self._database_wallet_identity()
        )

        current_accounts = {
            account.account_id: account
            for account in ring.accounts()
        }

        stored_accounts = {}

        for record in stored[
            "accounts"
        ]:
            if (
                not isinstance(
                    record,
                    dict,
                )
                or not isinstance(
                    record.get("id"),
                    str,
                )
                or record["id"]
                in stored_accounts
            ):
                raise RuntimeError(
                    "WALLET_IDENTITY_MISMATCH"
                )

            stored_accounts[
                record["id"]
            ] = record

        if (
            set(current_accounts)
            != set(stored_accounts)
        ):
            raise RuntimeError(
                "WALLET_IDENTITY_MISMATCH"
            )

        changed = False

        for identifier, account in (
            current_accounts.items()
        ):
            current = account.identity()
            stored_account = (
                stored_accounts[
                    identifier
                ]
            )

            for field in (
                "id",
                "epoch",
                "scan_public",
                "spend_public",
                "birthday",
            ):
                if (
                    stored_account.get(
                        field
                    )
                    != current.get(
                        field
                    )
                ):
                    raise RuntimeError(
                        "WALLET_IDENTITY_MISMATCH"
                    )

            labels = stored_account.get(
                "labels"
            )

            if (
                not isinstance(
                    labels,
                    list,
                )
                or len(labels)
                != len(set(labels))
                or any(
                    type(label) is not int
                    or not 1 <= label < 2**32
                    for label in labels
                )
            ):
                raise RuntimeError(
                    "WALLET_IDENTITY_MISMATCH"
                )

            stored_labels = set(
                labels
            )
            current_labels = set(
                account.labels
            )

            if not current_labels <= stored_labels:
                raise RuntimeError(
                    "WALLET_IDENTITY_MISMATCH"
                )

            for label in sorted(
                stored_labels
                - current_labels
            ):
                ring.add_label(
                    account.epoch,
                    label,
                )
                changed = True

        final_accounts = {
            account.account_id: (
                account.identity()
            )
            for account in ring.accounts()
        }

        if final_accounts != {
            identifier: stored_accounts[
                identifier
            ]
            for identifier in final_accounts
        }:
            raise RuntimeError(
                "WALLET_IDENTITY_MISMATCH"
            )

        return changed

    def _persist_keyring(
        self,
        ring: Keyring,
        passphrase,
    ):
        try:
            atomic_replace_keyring(
                self.keys_path,
                ring,
                self._password_bytes(
                    passphrase
                ),
            )
        except Exception as exc:
            raise RuntimeError(
                "WALLET_KEYS_REWRITE_FAILED"
            ) from exc

    def _open(self, passphrase):
        password = self._password_bytes(passphrase)

        if not self.exists():
            raise ValueError("WALLET_NOT_FOUND")

        self._validate_startup_fileset()
        self._validate_keys_preflight()
        self._validate_database_preflight()

        encrypted = load_private(
            self.keys_path
        )

        ring = None
        wallet = None

        try:
            ring, legacy_source = (
                restore_keyring(
                    encrypted,
                    password,
                )
            )

            metadata_recovered = (
                self._reconcile_keyring_metadata(
                    ring
                )
            )

            wallet = SilentWallet(
                self.db_path,
                ring.accounts(),
            )

            if (
                legacy_source
                or metadata_recovered
            ):
                self._persist_keyring(
                    ring,
                    password,
                )

            return ring, wallet

        except Exception:
            if wallet is not None:
                wallet.close()

            if ring is not None:
                ring.close()

            raise

    def _open_scanner_wallet(
        self,
        passphrase,
    ):
        ring, wallet = self._open(
            passphrase
        )

        ring.close()

        return wallet

    def _open_keyring(
        self,
        passphrase,
    ):
        ring, wallet = self._open(
            passphrase
        )

        wallet.close()

        return ring

    def verify_passphrase(self, passphrase: SecretMaterial) -> dict:
        """
        Validate the wallet passphrase without exposing private keys.

        Returns only public/session-safe wallet identity information.
        """
        ring, wallet = self._open(passphrase)

        try:
            address = wallet.get_silent_address()

            return {
                "valid": True,
                "address": address,
                "accounts": len(ring.accounts()),
            }

        finally:
            wallet.close()
            ring.close()

    def receive_address(self, passphrase: SecretMaterial) -> str:
        wallet = self._open_scanner_wallet(
            passphrase
        )

        try:
            return wallet.get_silent_address()
        finally:
            wallet.close()

    def receive_addresses(self, passphrase: SecretMaterial) -> list[dict]:
        """
        Return the base address plus all registered labeled addresses.
        """
        wallet = self._open_scanner_wallet(
            passphrase
        )

        try:
            result = [
                {
                    "label": None,
                    "name": "Base",
                    "epoch": wallet._account(None).epoch,
                    "address": wallet.get_silent_address(),
                }
            ]

            accounts = {
                account.account_id: account
                for account in wallet.scanner.accounts
            }

            rows = wallet.scanner.store.db.execute(
                """
                SELECT account, label, name
                FROM labels
                ORDER BY label
                """
            ).fetchall()

            for row in rows:
                account = accounts[row["account"]]

                result.append(
                    {
                        "label": row["label"],
                        "name": row["name"],
                        "epoch": account.epoch,
                        "address": wallet.get_silent_address(
                            epoch=account.epoch,
                            label=row["label"],
                        ),
                    }
                )

            return result

        finally:
            wallet.close()

    def create_labeled_address(
        self,
        passphrase: SecretMaterial,
        name: str,
    ) -> dict:
        """
        Allocate one new WSP label and persist that metadata in both:
          - wallet.db
          - encrypted keys.wsp

        The replacement of keys.wsp is atomic.
        """
        if not isinstance(name, str):
            raise ValueError("LABEL_NAME")

        name = name.strip()

        if not name:
            raise ValueError("LABEL_NAME_REQUIRED")

        if len(name) > 128:
            raise ValueError("LABEL_NAME")

        ring, wallet = self._open(passphrase)

        try:
            account = max(
                ring.accounts(),
                key=lambda item: item.epoch,
            )

            next_label = (
                max(account.labels, default=0) + 1
            )

            if next_label >= 2**32:
                raise ValueError("LABEL_LIMIT")

            ring.add_label(
                account.epoch,
                next_label,
            )

            # Database metadata commits first. If termination happens
            # before keys.wsp replacement, _open() reconciles the
            # committed label and rewrites keys.wsp deterministically.
            created = wallet.create_labeled_address(
                name=name,
                epoch=account.epoch,
                label=next_label,
            )

            self._persist_keyring(
                ring,
                passphrase,
            )

            return {
                "label": created["label"],
                "epoch": created["epoch"],
                "name": name,
                "address": created["address"],
            }

        finally:
            wallet.close()
            ring.close()

    def create_recovery_bundle(
        self,
        passphrase: SecretMaterial,
    ) -> dict:
        """
        Create an authenticated WSP-1 recovery bundle.

        The bundle contains encrypted key material, descriptors,
        labels and local wallet metadata. Blockchain state itself
        is reconstructed from a validating WAM node after restore.
        """
        ring, wallet = self._open(passphrase)

        backup_dir = (
            self.data_dir
            / "Backups"
        )

        harden_private_directory(
            backup_dir,
            create=True,
            code="WALLET_BACKUP_DIRECTORY_UNSAFE",
        )

        timestamp = datetime.now().strftime(
            "%Y%m%d-%H%M%S-%f"
        )

        backup_path = backup_dir / (
            f"wam-silent-recovery-{timestamp}.wspbak"
        )

        try:
            envelope = create_recovery(
                ring,
                wallet.scanner,
                self._password_bytes(passphrase),
            )

            # save_private uses O_EXCL + 0600 and refuses
            # unsafe/private-directory violations.
            save_private(
                backup_path,
                envelope,
            )

            harden_private_file(
                backup_path,
                required=True,
                code="WALLET_BACKUP_FILE_UNSAFE",
            )

            digest = hashlib.sha256(
                envelope
            ).hexdigest()

            accounts = ring.accounts()

            return {
                "path": str(backup_path),
                "size": len(envelope),
                "sha256": digest,
                "accounts": len(accounts),
                "labels": sum(
                    len(account.labels)
                    for account in accounts
                ),
            }

        finally:
            wallet.close()
            ring.close()

    def verify_recovery_bundle(
        self,
        passphrase: SecretMaterial,
        backup_path: str,
    ) -> dict:
        """
        Perform a real recovery into a disposable temporary database.

        The active wallet.db and keys.wsp are never replaced or
        modified by this verification.
        """
        path = Path(backup_path).expanduser()

        if not path.is_file():
            raise ValueError("RECOVERY_FILE_NOT_FOUND")

        envelope = load_private(
            path
        )

        digest = hashlib.sha256(
            envelope
        ).hexdigest()

        temp_root = Path(
            tempfile.mkdtemp(
                prefix=".wsp-recovery-verify-",
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

            restored_db = (
                temp_root
                / "restored-wallet.db"
            )

            ring, scanner = restore_recovery(
                envelope,
                self._password_bytes(passphrase),
                restored_db,
            )

            try:
                accounts = ring.accounts()

                if not accounts:
                    raise ValueError(
                        "RECOVERY_NO_ACCOUNTS"
                    )

                base_address = (
                    accounts[0]
                    .payment_code()
                )

                labels = sum(
                    len(account.labels)
                    for account in accounts
                )

                label_rows = scanner.store.db.execute(
                    "SELECT COUNT(*) FROM labels"
                ).fetchone()[0]

                contact_rows = scanner.store.db.execute(
                    "SELECT COUNT(*) FROM contacts"
                ).fetchone()[0]

                reservation_rows = scanner.store.db.execute(
                    "SELECT COUNT(*) FROM reservations"
                ).fetchone()[0]

                return {
                    "sha256": digest,
                    "accounts": len(accounts),
                    "labels": labels,
                    "label_rows": label_rows,
                    "contacts": contact_rows,
                    "reservations": reservation_rows,
                    "base_address": base_address,
                    "database_created": restored_db.is_file(),
                }

            finally:
                scanner.close()
                ring.close()

        finally:
            shutil.rmtree(
                temp_root,
                ignore_errors=True,
            )

    def restore_recovery_bundle(
        self,
        passphrase: SecretMaterial,
        backup_path: str,
    ) -> dict:
        """Restore into staging, validate, then activate with rollback."""
        return self.recovery.restore(
            passphrase,
            backup_path,
        )

    def reconcile_recovery(
        self,
        passphrase: SecretMaterial,
        chain,
    ) -> dict:
        if not self.recovery.pending():
            raise ValueError(
                "RECOVERY_NOT_PENDING"
            )

        ring, wallet = self._open(
            passphrase
        )

        try:
            return self.recovery.reconcile(
                wallet,
                chain,
            )

        finally:
            wallet.close()
            ring.close()

    def recovery_pending(
        self,
    ) -> bool:
        return self.recovery.pending()

    def recovery_pending_info(
        self,
    ):
        return self.recovery.pending_info()

    def assert_spend_ready(
        self,
    ):
        if self.recovery.pending():
            raise ValueError(
                "RECOVERY_RESCAN_REQUIRED"
            )

        if (
            self.payment_journal
            .has_unresolved()
        ):
            raise ValueError(
                "PAYMENT_RECONCILIATION_REQUIRED"
            )

    def reconcile_payment_journal(
        self,
        passphrase: SecretMaterial,
        chain,
    ) -> dict:
        wallet = (
            self._open_scanner_wallet(
                passphrase
            )
        )

        try:
            return (
                self.payment_reconciliation
                .reconcile(
                    wallet,
                    chain,
                )
            )

        finally:
            wallet.close()

    def validate_shutdown_integrity(
        self,
    ) -> dict:
        """
        Validate the persistent wallet fileset after all active
        workers have been joined and before the process lock is
        released.

        The WSP store uses SQLite journal_mode=DELETE with
        synchronous=FULL, so shutdown validation is based on
        filesystem preflight + SQLite quick_check rather than a
        WAL checkpoint.
        """
        self._validate_startup_fileset()

        if not self.db_path.exists():
            return {
                "wallet_exists": False,
                "database": "absent",
                "keys": "absent",
                "unresolved_payments": 0,
            }

        self._validate_database_preflight()
        self._validate_keys_preflight()

        unresolved = (
            self.payment_journal
            .unresolved()
        )

        return {
            "wallet_exists": True,
            "database": "ok",
            "keys": "ok",
            "unresolved_payments": len(
                unresolved
            ),
        }

    @staticmethod
    def amount_to_atoms(amount_text: str) -> int:
        """
        Convert a human WAM amount to integer atoms without float math.
        WAM uses 8 decimal places.
        """
        if not isinstance(amount_text, str):
            raise ValueError("AMOUNT_FORMAT")

        text = amount_text.strip()

        if not text:
            raise ValueError("AMOUNT_REQUIRED")

        try:
            amount = Decimal(text)
        except InvalidOperation:
            raise ValueError("AMOUNT_FORMAT") from None

        if not amount.is_finite() or amount <= 0:
            raise ValueError("AMOUNT_RANGE")

        atoms_value = amount * Decimal(ATOMS_PER_WAM)

        if atoms_value != atoms_value.to_integral_value():
            raise ValueError("AMOUNT_PRECISION")

        atoms = int(atoms_value)

        # WSP wallet policy/dust lower bound.
        if atoms < 330:
            raise ValueError("AMOUNT_TOO_SMALL")

        if atoms > 22_000_000 * ATOMS_PER_WAM:
            raise ValueError("AMOUNT_RANGE")

        return atoms

    def send_payment(
        self,
        passphrase: SecretMaterial,
        chain,
        destination: str,
        amount_text: str,
        fee_atoms: int = 1000,
    ) -> dict:
        """
        Legacy direct-signing entry point.

        Signing must pass through PaymentService -> SigningManifest
        -> SignerService.  Keeping this method fail-closed prevents
        future callers from accidentally bypassing the transaction
        approval boundary.
        """
        raise RuntimeError(
            "LEGACY_SIGNING_PATH_DISABLED"
        )

    def _verified_scanner_snapshot(
        self,
        passphrase: SecretMaterial,
        chain,
    ) -> dict:
        wallet = (
            self._open_scanner_wallet(
                passphrase
            )
        )

        try:
            metrics = wallet.scan(
                chain,
                mempool=True,
            )

            return build_scanner_snapshot(
                wallet,
                metrics,
            )

        finally:
            wallet.close()

    def scan_snapshot(
        self,
        passphrase: SecretMaterial,
        chain,
    ) -> dict:
        snapshot = (
            self._verified_scanner_snapshot(
                passphrase,
                chain,
            )
        )

        return {
            "scan_blocks": (
                snapshot["scan_blocks"]
            ),
            "scan_transactions": (
                snapshot[
                    "scan_transactions"
                ]
            ),
            "scan_candidates": (
                snapshot[
                    "scan_candidates"
                ]
            ),
            "scan_rollback": (
                snapshot[
                    "scan_rollback"
                ]
            ),
            "confirmed_atoms": (
                snapshot[
                    "confirmed_atoms"
                ]
            ),
            "available_atoms": (
                snapshot[
                    "available_atoms"
                ]
            ),
            "unconfirmed_atoms": (
                snapshot[
                    "unconfirmed_atoms"
                ]
            ),
            "pending_spent_atoms": (
                snapshot[
                    "pending_spent_atoms"
                ]
            ),
            "payments": (
                snapshot[
                    "payments_count"
                ]
            ),
            "history": (
                snapshot[
                    "history_count"
                ]
            ),
            "snapshot_fingerprint": (
                snapshot[
                    "snapshot_fingerprint"
                ]
            ),
        }

    def payments_snapshot(
        self,
        passphrase: SecretMaterial,
        chain,
    ) -> dict:
        snapshot = (
            self._verified_scanner_snapshot(
                passphrase,
                chain,
            )
        )

        return {
            "scan_blocks": (
                snapshot["scan_blocks"]
            ),
            "scan_transactions": (
                snapshot[
                    "scan_transactions"
                ]
            ),
            "scan_candidates": (
                snapshot[
                    "scan_candidates"
                ]
            ),
            "scan_rollback": (
                snapshot[
                    "scan_rollback"
                ]
            ),
            "count": (
                snapshot[
                    "payments_count"
                ]
            ),
            "payments": (
                snapshot[
                    "payments"
                ]
            ),
            "scanner_tip_height": (
                snapshot[
                    "scanner_tip_height"
                ]
            ),
            "scanner_tip_hash": (
                snapshot[
                    "scanner_tip_hash"
                ]
            ),
            "snapshot_fingerprint": (
                snapshot[
                    "snapshot_fingerprint"
                ]
            ),
        }

    def background_sync_snapshot(
        self,
        passphrase: SecretMaterial,
        chain,
    ) -> dict:
        """
        Perform one complete chain+mempool scan and expose only a
        verified, normalized application snapshot.
        """
        return self._verified_scanner_snapshot(
            passphrase,
            chain,
        )
