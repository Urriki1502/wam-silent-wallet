from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..services.payment_service import PaymentService


class SendPage(QWidget):
    def __init__(
        self,
        wallet_service,
        node_service,
        session_service,
        default_fee_tier="Normal",
        parent=None,
    ):
        super().__init__(parent)

        self.wallet_service = wallet_service
        self.node_service = node_service
        self.session_service = session_service
        self.default_fee_tier = (
            default_fee_tier
            if default_fee_tier in {
                "Economy",
                "Normal",
                "Priority",
            }
            else "Normal"
        )

        self.payment_service = (
            PaymentService(
                wallet_service,
                node_service,
            )
        )

        self.last_txid = None
        self.last_fee_quote = None

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
            "Review, sign and broadcast a WSP-1 Silent Payment "
            "through the local WAM regtest node."
        )

        description.setWordWrap(True)

        layout.addWidget(description)

        destination_label = QLabel(
            "Silent Payment destination"
        )

        self.destination = QLineEdit()

        self.destination.setPlaceholderText(
            "wamrtsp1..."
        )

        layout.addWidget(
            destination_label
        )

        layout.addWidget(
            self.destination
        )

        amount_label = QLabel(
            "Amount (WAM)"
        )

        self.amount = QLineEdit()

        self.amount.setPlaceholderText(
            "0.25000000"
        )

        layout.addWidget(
            amount_label
        )

        layout.addWidget(
            self.amount
        )

        fee_heading = QLabel(
            "Fee policy"
        )

        fee_heading.setStyleSheet(
            "font-weight: 700; "
            "padding-top: 14px;"
        )

        layout.addWidget(
            fee_heading
        )

        self.fee_tier = QComboBox()

        self.fee_tier.addItems(
            [
                "Economy",
                "Normal",
                "Priority",
            ]
        )

        self.fee_tier.setCurrentText(
            self.default_fee_tier
        )

        self.fee_tier.currentTextChanged.connect(
            self.refresh_fee_quote
        )

        layout.addWidget(
            self.fee_tier
        )

        self.fee_detail = QLabel(
            "Reading WAM Core fee policy..."
        )

        self.fee_detail.setWordWrap(
            True
        )

        layout.addWidget(
            self.fee_detail
        )

        self.refresh_fee_button = QPushButton(
            "Refresh fee quote"
        )

        self.refresh_fee_button.clicked.connect(
            self.refresh_fee_quote
        )

        layout.addWidget(
            self.refresh_fee_button
        )

        self.send_button = QPushButton(
            "Review & Send on REGTEST"
        )

        self.send_button.clicked.connect(
            self.send_payment
        )

        layout.addWidget(
            self.send_button
        )

        self.status = QLabel(
            "No transaction created."
        )

        self.status.setWordWrap(
            True
        )

        layout.addWidget(
            self.status
        )

        txid_label = QLabel(
            "Broadcast TXID"
        )

        txid_label.setStyleSheet(
            "font-weight: 700; "
            "padding-top: 18px;"
        )

        layout.addWidget(
            txid_label
        )

        self.txid = QLineEdit()

        self.txid.setReadOnly(
            True
        )

        self.txid.setPlaceholderText(
            "TXID will appear after successful broadcast"
        )

        layout.addWidget(
            self.txid
        )

        self.copy_button = QPushButton(
            "Copy TXID"
        )

        self.copy_button.setEnabled(
            False
        )

        self.copy_button.clicked.connect(
            self.copy_txid
        )

        layout.addWidget(
            self.copy_button
        )

        warning = QLabel(
            "EXPERIMENTAL — REGTEST ONLY. "
            "Fee policy is read from the configured WAM Core node. "
            "The final fee is reviewed before the WSP transaction is signed."
        )

        warning.setWordWrap(
            True
        )

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

        layout.addWidget(
            warning
        )

        layout.addStretch()

        self.refresh_fee_quote()

    def set_default_fee_tier(
        self,
        tier: str,
    ):
        if tier not in {
            "Economy",
            "Normal",
            "Priority",
        }:
            raise ValueError(
                "CONFIG_FEE_TIER"
            )

        self.default_fee_tier = tier

        self.fee_tier.setCurrentText(
            tier
        )

    def refresh_fee_quote(self):
        self.refresh_fee_button.setEnabled(
            False
        )

        try:
            quote = (
                self.payment_service
                .fees
                .quote(
                    self.fee_tier
                    .currentText()
                )
            )

            fee_atoms, vsize = (
                self.payment_service
                .fees
                .fee_for(
                    quote["atoms_per_vb"],
                    1,
                    2,
                )
            )

            self.last_fee_quote = quote

            self.fee_detail.setText(
                f'{quote["tier"]}: '
                f'{quote["atoms_per_vb"]} atom/vB · '
                f'~{vsize} vB for a 1-input/2-output payment · '
                f'~{fee_atoms / 100_000_000:.8f} WAM. '
                f'Source: {quote["source"]}.'
            )

        except Exception:
            self.last_fee_quote = None

            self.fee_detail.setText(
                "Fee quote unavailable. "
                "Check WAM Core node status."
            )

        finally:
            self.refresh_fee_button.setEnabled(
                True
            )

    def send_payment(self):
        destination = (
            self.destination
            .text()
            .strip()
        )

        amount = (
            self.amount
            .text()
            .strip()
        )

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

        self.send_button.setEnabled(
            False
        )

        self.status.setText(
            "Synchronizing wallet and preparing fee review..."
        )

        QApplication.processEvents()

        review = None

        try:
            with (
                self.session_service
                .secret_lease()
            ) as secret:
                review = (
                    self.payment_service
                    .review(
                        secret,
                        destination,
                        amount,
                        self.fee_tier
                        .currentText(),
                    )
                )

            amount_normalized = (
                f"{atoms / 100_000_000:.8f}"
            )

            message = (
                f"Send {amount_normalized} WAM?\n\n"
                f"Fee tier: {review.tier}\n"
                f"Fee rate: {review.fee_rate_atoms_vb} atom/vB\n"
                f"Estimated vsize: {review.estimated_vsize} vB\n"
                f"Fee: {review.fee_wam:.8f} WAM "
                f"({review.fee_atoms:,} atoms)\n"
                f"Inputs: {review.input_count}\n"
                f"Outputs: {review.output_count}\n"
                f"Fee source: {review.fee_source}\n\n"
                "The transaction has not been signed yet."
            )

            answer = QMessageBox.question(
                self,
                "Confirm REGTEST Silent Payment",
                message,
                QMessageBox.Yes
                | QMessageBox.No,
                QMessageBox.No,
            )

            if answer != QMessageBox.Yes:
                with (
                    self.session_service
                    .secret_lease()
                ) as secret:
                    self.payment_service.cancel(
                        secret,
                        review,
                    )

                review = None

                self.status.setText(
                    "Payment cancelled. "
                    "Draft coin reservation released."
                )

                return

            self.status.setText(
                "Signing, policy-checking and broadcasting..."
            )

            QApplication.processEvents()

            with (
                self.session_service
                .secret_lease()
            ) as secret:
                result = (
                    self.payment_service
                    .broadcast(
                        secret,
                        review,
                    )
                )

            review = None

            self.last_txid = result[
                "txid"
            ]

            self.txid.setText(
                result["txid"]
            )

            self.copy_button.setEnabled(
                True
            )

            self.status.setText(
                "Broadcast successful — "
                f'{result["amount_wam"]:.8f} WAM sent, '
                f'{result["fee_wam"]:.8f} WAM fee '
                f'@ {result["fee_rate_atoms_vb"]} atom/vB, '
                f'{result["inputs"]} input(s). '
                "Waiting for confirmation."
            )

            self.destination.clear()
            self.amount.clear()

            self.refresh_fee_quote()

        except Exception as exc:
            self.last_txid = None

            self.txid.clear()

            self.copy_button.setEnabled(
                False
            )

            # If the failure occurred before PaymentService took over
            # cleanup, a still-draft review can be released here.
            if review is not None:
                try:
                    with (
                        self.session_service
                        .secret_lease()
                    ) as secret:
                        self.payment_service.cancel(
                            secret,
                            review,
                        )
                except Exception:
                    pass

            self.status.setText(
                "Transaction failed. "
                "Check destination, amount, balance, "
                "fee policy and node status."
            )

            print(
                "Send failure:",
                type(exc).__name__,
                str(exc),
            )

        finally:
            self.send_button.setEnabled(
                True
            )

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
