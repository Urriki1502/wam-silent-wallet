from pathlib import Path

from PySide6.QtCore import Signal

from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class BackupPage(QWidget):
    reconcile_requested = Signal()

    def __init__(
        self,
        wallet_service,
        session_service,
        parent=None,
    ):
        super().__init__(parent)

        self.wallet_service = wallet_service
        self.session_service = session_service

        self.last_backup_path = None

        self._build()
        self.refresh_recovery_state()

    def _build(self):
        layout = QVBoxLayout(self)

        heading = QLabel(
            "Backup & Recovery"
        )

        heading.setStyleSheet(
            "font-size: 26px; "
            "font-weight: 700; "
            "padding: 20px;"
        )

        layout.addWidget(heading)

        description = QLabel(
            "Create and verify an authenticated WSP-1 recovery "
            "bundle containing encrypted keys, descriptors, labels "
            "and local wallet metadata. Blockchain state is rebuilt "
            "from a validating WAM node after recovery."
        )

        description.setWordWrap(True)

        layout.addWidget(description)

        # ------------------------------------------------------
        # Create
        # ------------------------------------------------------

        self.create_button = QPushButton(
            "Create Recovery Bundle"
        )

        self.create_button.clicked.connect(
            self.create_backup
        )

        layout.addWidget(
            self.create_button
        )

        # ------------------------------------------------------
        # Bundle path
        # ------------------------------------------------------

        path_label = QLabel(
            "Recovery bundle"
        )

        path_label.setStyleSheet(
            "font-weight: 700; "
            "padding-top: 18px;"
        )

        layout.addWidget(path_label)

        self.path_field = QLineEdit()

        self.path_field.setReadOnly(True)

        self.path_field.setPlaceholderText(
            "No recovery bundle selected"
        )

        layout.addWidget(
            self.path_field
        )

        self.select_button = QPushButton(
            "Select Recovery Bundle"
        )

        self.select_button.clicked.connect(
            self.select_backup
        )

        layout.addWidget(
            self.select_button
        )

        self.copy_path_button = QPushButton(
            "Copy Backup Path"
        )

        self.copy_path_button.setEnabled(False)

        self.copy_path_button.clicked.connect(
            self.copy_path
        )

        layout.addWidget(
            self.copy_path_button
        )

        # ------------------------------------------------------
        # Verify
        # ------------------------------------------------------

        self.verify_button = QPushButton(
            "Verify Recovery Bundle"
        )

        self.verify_button.clicked.connect(
            self.verify_backup
        )

        layout.addWidget(
            self.verify_button
        )

        # ------------------------------------------------------
        # Reconciliation after active restore
        # ------------------------------------------------------

        recovery_heading = QLabel(
            "Recovered wallet state"
        )

        recovery_heading.setStyleSheet(
            "font-weight: 700; "
            "padding-top: 18px;"
        )

        layout.addWidget(
            recovery_heading
        )

        self.recovery_status = QLabel(
            "Checking recovery state..."
        )

        self.recovery_status.setWordWrap(
            True
        )

        layout.addWidget(
            self.recovery_status
        )

        self.reconcile_button = QPushButton(
            "Reconcile Recovered Wallet with WAM Node"
        )

        self.reconcile_button.clicked.connect(
            self.request_reconcile
        )

        layout.addWidget(
            self.reconcile_button
        )

        # ------------------------------------------------------
        # Result
        # ------------------------------------------------------

        self.status = QLabel(
            "No recovery operation performed."
        )

        self.status.setWordWrap(True)

        layout.addWidget(
            self.status
        )

        self.details = QLabel("")
        self.details.setWordWrap(True)

        layout.addWidget(
            self.details
        )

        warning = QLabel(
            "Recovery bundles contain encrypted private key material. "
            "Do not upload them publicly, commit them to Git, or share "
            "them together with the wallet passphrase."
        )

        warning.setWordWrap(True)

        warning.setStyleSheet(
            """
            QLabel {
                margin-top: 18px;
                padding: 10px;
                border: 1px solid #999;
                font-weight: 600;
            }
            """
        )

        layout.addWidget(warning)

        layout.addStretch()

    def create_backup(self):
        self.create_button.setEnabled(False)

        try:
            with (
                self.session_service
                .secret_lease()
            ) as secret:
                result = (
                    self.wallet_service
                    .create_recovery_bundle(
                        secret
                    )
                )

            self.last_backup_path = (
                result["path"]
            )

            self.path_field.setText(
                result["path"]
            )

            self.copy_path_button.setEnabled(
                True
            )

            self.status.setText(
                "Recovery bundle created successfully."
            )

            self.details.setText(
                f'Accounts: {result["accounts"]}\n'
                f'Labels: {result["labels"]}\n'
                f'Size: {result["size"]} bytes\n'
                f'SHA256: {result["sha256"]}'
            )

        except Exception as exc:
            self.status.setText(
                "Unable to create recovery bundle."
            )

            self.details.setText("")

            print(
                "Backup failure:",
                type(exc).__name__,
                str(exc),
            )

        finally:
            self.create_button.setEnabled(True)

    def select_backup(self):
        initial_dir = (
            self.wallet_service.data_dir
            / "Backups"
        )

        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select WSP Recovery Bundle",
            str(initial_dir),
            "WSP Recovery Bundle (*.wspbak);;All Files (*)",
        )

        if not filename:
            return

        self.last_backup_path = filename

        self.path_field.setText(
            filename
        )

        self.copy_path_button.setEnabled(
            True
        )

        self.status.setText(
            "Recovery bundle selected."
        )

        self.details.setText("")

    def verify_backup(self):
        if not self.last_backup_path:
            self.status.setText(
                "Create or select a recovery bundle first."
            )
            return

        self.verify_button.setEnabled(False)

        try:
            with (
                self.session_service
                .secret_lease()
            ) as secret:
                result = (
                    self.wallet_service
                    .verify_recovery_bundle(
                        secret,
                        self.last_backup_path,
                    )
                )

            short_address = (
                result["base_address"][:22]
                + "..."
                + result["base_address"][-16:]
            )

            self.status.setText(
                "Recovery verification: PASS"
            )

            self.details.setText(
                f'Accounts: {result["accounts"]}\n'
                f'Labels: {result["labels"]}\n'
                f'Label records: {result["label_rows"]}\n'
                f'Contacts: {result["contacts"]}\n'
                f'Reservations: {result["reservations"]}\n'
                f'Base address: {short_address}\n'
                f'SHA256: {result["sha256"]}'
            )

        except Exception as exc:
            self.status.setText(
                "Recovery verification failed."
            )

            self.details.setText(
                "The passphrase may be incorrect, "
                "or the recovery bundle may be invalid."
            )

            print(
                "Recovery verification failure:",
                type(exc).__name__,
                str(exc),
            )

        finally:
            self.verify_button.setEnabled(True)

    def copy_path(self):
        if not self.last_backup_path:
            return

        QApplication.clipboard().setText(
            self.last_backup_path
        )

        self.status.setText(
            "Backup path copied."
        )

    def refresh_recovery_state(self):
        try:
            info = (
                self.wallet_service
                .recovery_pending_info()
            )

        except Exception:
            self.recovery_status.setText(
                "Recovery state is invalid. "
                "Spending remains blocked."
            )

            self.reconcile_button.setEnabled(
                False
            )

            return

        if info is None:
            self.recovery_status.setText(
                "No recovery reconciliation pending."
            )

            self.reconcile_button.setEnabled(
                False
            )

            return

        address = info["base_address"]

        short = (
            address[:22]
            + "..."
            + address[-16:]
        )

        self.recovery_status.setText(
            "RECOVERY PENDING — spending is blocked "
            "until the restored wallet is reconciled "
            "with the validating WAM node.\n"
            f"Wallet: {short}\n"
            f'SHA256: {info["sha256"]}'
        )

        self.reconcile_button.setEnabled(
            True
        )

    def request_reconcile(self):
        if not (
            self.wallet_service
            .recovery_pending()
        ):
            self.refresh_recovery_state()
            return

        self.reconcile_button.setEnabled(
            False
        )

        self.recovery_status.setText(
            "Reconciling recovered wallet with "
            "confirmed chain and mempool..."
        )

        self.reconcile_requested.emit()

    def show_reconcile_success(
        self,
        result: dict,
    ):
        self.recovery_status.setText(
            "Recovery reconciliation: PASS\n"
            f'Blocks scanned: {result["scan_blocks"]}\n'
            f'Transactions scanned: '
            f'{result["scan_transactions"]}\n'
            f'Confirmed locks resolved: '
            f'{result["resolved_confirmed"]}\n'
            f'Uncertain locks retained: '
            f'{result["uncertain_locked"]}\n'
            f'Manual locks retained: '
            f'{result["manual_locked"]}\n'
            "Spending gate cleared."
        )

        self.reconcile_button.setEnabled(
            False
        )

    def show_reconcile_failure(
        self,
    ):
        self.recovery_status.setText(
            "Recovery reconciliation failed. "
            "Spending remains blocked."
        )

        self.reconcile_button.setEnabled(
            True
        )
