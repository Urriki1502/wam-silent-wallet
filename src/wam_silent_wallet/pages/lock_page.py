from PySide6.QtCore import Qt, Signal

from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class LockPage(QWidget):
    unlocked = Signal()

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

        self.message = QLabel("")

        self.message.setAlignment(
            Qt.AlignCenter
        )

        self.message.setWordWrap(True)

        outer.addWidget(self.message)

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
        password = self.passphrase.text()

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

    def reset(self):
        self.passphrase.clear()

        self.message.setText(
            "Wallet locked."
        )

        self.passphrase.setFocus()
