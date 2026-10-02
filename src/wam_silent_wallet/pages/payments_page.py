from PySide6.QtCore import Qt

from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class PaymentsPage(QWidget):
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

        self._build()

    def _build(self):
        layout = QVBoxLayout(self)

        heading = QLabel("Payments")

        heading.setStyleSheet(
            "font-size: 26px; "
            "font-weight: 700; "
            "padding: 20px;"
        )

        layout.addWidget(heading)

        description = QLabel(
            "Confirmed Silent Payments detected "
            "by the local WSP-1 scanner."
        )

        layout.addWidget(description)

        self.refresh_button = QPushButton(
            "Refresh payments"
        )

        self.refresh_button.clicked.connect(
            self.refresh_payments
        )

        layout.addWidget(
            self.refresh_button
        )

        self.status = QLabel(
            "Payments not loaded."
        )

        self.status.setStyleSheet(
            "font-weight: 600;"
        )

        layout.addWidget(
            self.status
        )

        self.table = QTableWidget(
            0,
            7,
        )

        self.table.setHorizontalHeaderLabels(
            [
                "Amount",
                "Block",
                "Conf.",
                "Label",
                "State",
                "TXID",
                "Vout",
            ]
        )

        self.table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )

        self.table.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )

        self.table.setSelectionMode(
            QAbstractItemView.SingleSelection
        )

        self.table.verticalHeader().setVisible(
            False
        )

        header = (
            self.table
            .horizontalHeader()
        )

        header.setSectionResizeMode(
            QHeaderView.ResizeToContents
        )

        header.setSectionResizeMode(
            5,
            QHeaderView.Stretch,
        )

        layout.addWidget(
            self.table
        )

        self.copy_button = QPushButton(
            "Copy selected TXID"
        )

        self.copy_button.setEnabled(
            False
        )

        self.copy_button.clicked.connect(
            self.copy_selected_txid
        )

        self.table.itemSelectionChanged.connect(
            self._selection_changed
        )

        layout.addWidget(
            self.copy_button
        )

        self.message = QLabel("")

        layout.addWidget(
            self.message
        )

    def refresh_payments(self):
        self.refresh_button.setEnabled(
            False
        )

        self.status.setText(
            "Synchronizing Silent Wallet..."
        )

        QApplication.processEvents()

        try:
            with (
                self.session_service
                .secret_lease()
            ) as secret:
                result = (
                    self.wallet_service
                    .payments_snapshot(
                        secret,
                        self.node_service
                        .scanner_chain(),
                    )
                )

            self.apply_snapshot(
                result,
                automatic=False,
            )

        except Exception:
            self.status.setText(
                "Unable to load payments."
            )

            self.message.setText(
                "Check WAM node status."
            )

        finally:
            self.refresh_button.setEnabled(
                True
            )

    def apply_snapshot(
        self,
        result: dict,
        *,
        automatic: bool = True,
    ):
        payments = result.get(
            "payments",
            [],
        )

        self.table.setRowCount(
            len(payments)
        )

        for row, payment in enumerate(
            payments
        ):
            label_text = (
                "Base"
                if payment["label"] is None
                else f'Label {payment["label"]}'
            )

            state_text = (
                "Available"
                if payment["spent"] is None
                else f'Spent @ {payment["spent"]}'
            )

            full_txid = payment["txid"]

            short_txid = (
                full_txid[:12]
                + "..."
                + full_txid[-12:]
            )

            txid = QTableWidgetItem(
                short_txid
            )

            txid.setData(
                Qt.UserRole,
                full_txid,
            )

            values = [
                QTableWidgetItem(
                    f'{payment["amount_wam"]:.8f} WAM'
                ),
                QTableWidgetItem(
                    str(payment["received"])
                ),
                QTableWidgetItem(
                    str(payment["confirmations"])
                ),
                QTableWidgetItem(
                    label_text
                ),
                QTableWidgetItem(
                    state_text
                ),
                txid,
                QTableWidgetItem(
                    str(payment["vout"])
                ),
            ]

            for column, item in enumerate(
                values
            ):
                self.table.setItem(
                    row,
                    column,
                    item,
                )

        count = result.get(
            "count",
            result.get(
                "payments_count",
                len(payments),
            ),
        )

        self.status.setText(
            f"{count} payment(s) detected."
        )

        self.message.setText(
            "Payments auto-synchronized."
            if automatic
            else "Payment history synchronized successfully."
        )

    def _selection_changed(self):
        self.copy_button.setEnabled(
            bool(
                self.table.selectedItems()
            )
        )

    def copy_selected_txid(self):
        selected = (
            self.table
            .selectionModel()
            .selectedRows()
        )

        if not selected:
            return

        row = selected[0].row()

        txid = (
            self.table
            .item(row, 5)
            .data(Qt.UserRole)
        )

        QApplication.clipboard().setText(
            txid
        )

        self.message.setText(
            "TXID copied to clipboard."
        )
