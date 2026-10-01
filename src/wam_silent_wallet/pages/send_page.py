from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class SendPage(QWidget):
    FIXED_FEE_ATOMS = 1000

    def __init__(
        self,
        wallet_service,
        node_service,
        session_service,
        parent=None,
    ):
        super().__init__(parent)

        self.wallet_service = wallet_service
        self.node_service = node_service
        self.session_service = session_service

        self.last_txid = None

        self._build()

    def _build(self):
        layout = QVBoxLayout(self)

        heading = QLabel("Send")
        heading.setStyleSheet(
            "font-size: 26px; "
            "font-weight: 700; "
            "padding: 20px;"
        )

        layout.addWidget(heading)

        description = QLabel(
            "Create, sign and broadcast a WSP-1 Silent Payment "
            "through the local WAM regtest node."
        )

        description.setWordWrap(True)

        layout.addWidget(description)

        # ------------------------------------------------------
        # Destination
        # ------------------------------------------------------

        destination_label = QLabel(
            "Silent Payment destination"
        )

        self.destination = QLineEdit()

        self.destination.setPlaceholderText(
            "wamrtsp1..."
        )

        layout.addWidget(destination_label)
        layout.addWidget(self.destination)

        # ------------------------------------------------------
        # Amount
        # ------------------------------------------------------

        amount_label = QLabel(
            "Amount (WAM)"
        )

        self.amount = QLineEdit()

        self.amount.setPlaceholderText(
            "0.25000000"
        )

        layout.addWidget(amount_label)
        layout.addWidget(self.amount)

        fee_label = QLabel(
            "Demo fee: 0.00001000 WAM "
            "(1,000 atoms)"
        )

        fee_label.setStyleSheet(
            "font-weight: 600;"
        )

        layout.addWidget(fee_label)

        # ------------------------------------------------------
        # Send button
        # ------------------------------------------------------

        self.send_button = QPushButton(
            "Send on REGTEST"
        )

        self.send_button.clicked.connect(
            self.send_payment
        )

        layout.addWidget(self.send_button)

        self.status = QLabel(
            "No transaction created."
        )

        self.status.setWordWrap(True)

        layout.addWidget(self.status)

        # ------------------------------------------------------
        # Result TXID
        # ------------------------------------------------------

        txid_label = QLabel(
            "Broadcast TXID"
        )

        txid_label.setStyleSheet(
            "font-weight: 700; "
            "padding-top: 18px;"
        )

        layout.addWidget(txid_label)

        self.txid = QLineEdit()

        self.txid.setReadOnly(True)

        self.txid.setPlaceholderText(
            "TXID will appear after successful broadcast"
        )

        layout.addWidget(self.txid)

        self.copy_button = QPushButton(
            "Copy TXID"
        )

        self.copy_button.setEnabled(False)

        self.copy_button.clicked.connect(
            self.copy_txid
        )

        layout.addWidget(self.copy_button)

        warning = QLabel(
            "EXPERIMENTAL — REGTEST ONLY. "
            "This screen signs real WSP transactions, "
            "but the configured node is an isolated WAM regtest node."
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

    def send_payment(self):
        destination = self.destination.text().strip()
        amount = self.amount.text().strip()
        password = self.session_service.passphrase()

        if not destination:
            self.status.setText(
                "Enter a Silent Payment destination."
            )
            return

        if not amount:
            self.status.setText(
                "Enter an amount."
            )
            return

        # Validate amount locally before asking for confirmation.
        try:
            atoms = (
                self.wallet_service
                .amount_to_atoms(amount)
            )
        except Exception:
            self.status.setText(
                "Invalid amount. "
                "Use a positive WAM value with "
                "no more than 8 decimal places."
            )
            return

        amount_normalized = (
            f"{atoms / 100_000_000:.8f}"
        )

        answer = QMessageBox.question(
            self,
            "Confirm REGTEST payment",
            (
                f"Send {amount_normalized} WAM?\n\n"
                f"Fee: 0.00001000 WAM\n\n"
                "This will construct, sign and broadcast "
                "a real WSP transaction on WAM regtest."
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if answer != QMessageBox.Yes:
            self.status.setText(
                "Payment cancelled."
            )
            return

        self.send_button.setEnabled(False)

        self.status.setText(
            "Constructing and signing transaction..."
        )

        QApplication.processEvents()

        try:
            result = (
                self.wallet_service
                .send_payment(
                    password,
                    self.node_service.broadcast_chain(),
                    destination,
                    amount,
                    self.FIXED_FEE_ATOMS,
                )
            )

            self.last_txid = result["txid"]

            self.txid.setText(
                result["txid"]
            )

            self.copy_button.setEnabled(
                True
            )

            self.status.setText(
                "Broadcast successful — "
                f'{result["amount_wam"]:.8f} WAM sent, '
                f'{result["fee_wam"]:.8f} WAM fee, '
                f'{result["inputs"]} input(s). '
                "Waiting for confirmation."
            )

            self.destination.clear()
            self.amount.clear()

        except Exception as exc:
            self.last_txid = None

            self.txid.clear()

            self.copy_button.setEnabled(
                False
            )

            # Keep backend exception codes out of normal UI.
            self.status.setText(
                "Transaction failed. "
                "Check destination, amount, balance, "
                "wallet passphrase and node status."
            )

            # Console-only diagnostic for this experimental build.
            print(
                "Send failure:",
                type(exc).__name__,
                str(exc),
            )

        finally:
            self.send_button.setEnabled(True)

    def copy_txid(self):
        if not self.last_txid:
            self.status.setText(
                "No TXID available."
            )
            return

        QApplication.clipboard().setText(
            self.last_txid
        )

        self.status.setText(
            "TXID copied to clipboard."
        )
