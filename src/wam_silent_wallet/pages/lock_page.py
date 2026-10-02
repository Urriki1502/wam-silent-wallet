from PySide6.QtCore import (
    Qt,
    Signal,
)

from PySide6.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class LockPage(QWidget):
    unlocked = Signal()

    # path, mutable recovery-passphrase lease
    restore_requested = Signal(
        str,
        object,
    )

    def __init__(
        self,
        session_service,
        parent=None,
    ):
        super().__init__(parent)

        self.session_service = (
            session_service
        )

        self._build()

    def _build(self):
        outer = QVBoxLayout(self)

        outer.addStretch()

        title = QLabel(
            "WAM Silent Wallet"
        )

        title.setAlignment(
            Qt.AlignCenter
        )

        title.setStyleSheet(
            "font-size: 32px; "
            "font-weight: 700;"
        )

        outer.addWidget(title)

        subtitle = QLabel(
            "Experimental — Regtest Only"
        )

        subtitle.setAlignment(
            Qt.AlignCenter
        )

        subtitle.setStyleSheet(
            "font-size: 16px; "
            "font-weight: 600; "
            "padding-bottom: 24px;"
        )

        outer.addWidget(subtitle)

        status = QLabel(
            "Wallet Locked"
        )

        status.setAlignment(
            Qt.AlignCenter
        )

        status.setStyleSheet(
            "font-size: 20px; "
            "font-weight: 700;"
        )

        outer.addWidget(status)

        self.passphrase = QLineEdit()

        self.passphrase.setEchoMode(
            QLineEdit.Password
        )

        self.passphrase.setPlaceholderText(
            "Wallet passphrase"
        )

        self.passphrase.setMaximumWidth(
            480
        )

        self.passphrase.returnPressed.connect(
            self.unlock_wallet
        )

        outer.addWidget(
            self.passphrase,
            alignment=Qt.AlignCenter,
        )

        self.unlock_button = QPushButton(
            "Unlock Wallet"
        )

        self.unlock_button.setMaximumWidth(
            480
        )

        self.unlock_button.clicked.connect(
            self.unlock_wallet
        )

        outer.addWidget(
            self.unlock_button,
            alignment=Qt.AlignCenter,
        )

        self.restore_button = QPushButton(
            "Restore from Recovery Bundle"
        )

        self.restore_button.setMaximumWidth(
            480
        )

        self.restore_button.clicked.connect(
            self.restore_wallet
        )

        outer.addWidget(
            self.restore_button,
            alignment=Qt.AlignCenter,
        )

        self.message = QLabel("")

        self.message.setAlignment(
            Qt.AlignCenter
        )

        self.message.setWordWrap(True)

        outer.addWidget(
            self.message
        )

        warning = QLabel(
            "REGTEST wallet — do not use this "
            "experimental build with real funds."
        )

        warning.setAlignment(
            Qt.AlignCenter
        )

        warning.setWordWrap(True)

        warning.setStyleSheet(
            "padding-top: 18px; "
            "font-weight: 600;"
        )

        outer.addWidget(warning)

        outer.addStretch()

    def unlock_wallet(self):
        password = (
            self.passphrase.text()
        )

        if not password:
            self.message.setText(
                "Enter the wallet passphrase."
            )
            return

        self.unlock_button.setEnabled(
            False
        )

        try:
            self.session_service.unlock(
                password
            )

            self.message.setText("")

            self.passphrase.clear()

            self.unlocked.emit()

        except Exception:
            self.passphrase.clear()

            self.message.setText(
                "Unable to unlock wallet. "
                "Check the passphrase."
            )

        finally:
            self.unlock_button.setEnabled(
                True
            )

    def restore_wallet(self):
        wallet_service = (
            self.session_service
            .wallet_service
        )

        initial_dir = (
            wallet_service.data_dir
            / "Backups"
        )

        filename, _ = (
            QFileDialog
            .getOpenFileName(
                self,
                "Select WSP Recovery Bundle",
                str(initial_dir),
                (
                    "WSP Recovery Bundle (*.wspbak);;"
                    "All Files (*)"
                ),
            )
        )

        if not filename:
            return

        if wallet_service.exists():
            text = (
                "This will replace the active wallet database "
                "and encrypted key file after the recovery bundle "
                "has been fully authenticated and staged.\n\n"
                "Continue?"
            )

        else:
            text = (
                "Restore this WSP recovery bundle "
                "as the active wallet?"
            )

        answer = QMessageBox.warning(
            self,
            "Restore Wallet",
            text,
            (
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
            ),
            QMessageBox.StandardButton.No,
        )

        if (
            answer
            != QMessageBox.StandardButton.Yes
        ):
            return

        password, accepted = (
            QInputDialog.getText(
                self,
                "Recovery Passphrase",
                (
                    "Enter the passphrase used "
                    "to create this recovery bundle:"
                ),
                QLineEdit.Password,
            )
        )

        if not accepted:
            return

        if not password:
            self.message.setText(
                "Recovery passphrase is required."
            )
            return

        secret = bytearray(
            password.encode(
                "utf-8"
            )
        )

        del password

        self.restore_button.setEnabled(
            False
        )

        self.unlock_button.setEnabled(
            False
        )

        self.message.setText(
            "Authenticating and staging recovery..."
        )

        try:
            self.restore_requested.emit(
                filename,
                secret,
            )

        finally:
            for index in range(
                len(secret)
            ):
                secret[index] = 0

    def _restore_controls_ready(
        self,
    ):
        self.restore_button.setEnabled(
            True
        )

        self.unlock_button.setEnabled(
            True
        )

    def show_restore_success(
        self,
        result: dict,
    ):
        self._restore_controls_ready()
        address = (
            result["base_address"]
        )

        short = (
            address[:22]
            + "..."
            + address[-16:]
        )

        self.message.setText(
            "Recovery activated successfully.\n"
            "Spending is locked until chain reconciliation.\n"
            f"Wallet: {short}\n"
            "Unlock with the recovery passphrase, then open "
            "Backup → Reconcile recovered wallet."
        )

    def show_restore_failure(
        self,
    ):
        self._restore_controls_ready()

        self.message.setText(
            "Recovery failed safely. "
            "The active wallet was not replaced."
        )

    def reset(self):
        self.passphrase.clear()

        self.message.setText(
            "Wallet locked."
        )

        self.passphrase.setFocus()
