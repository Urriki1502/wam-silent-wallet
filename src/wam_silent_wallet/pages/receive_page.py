from PySide6.QtCore import Qt

from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class ReceivePage(QWidget):
    def __init__(
        self,
        wallet_service,
        session_service,
        parent=None,
    ):
        super().__init__(parent)

        self.wallet_service = wallet_service
        self.session_service = session_service

        self._build()

        self.load_addresses()

    def _build(self):
        layout = QVBoxLayout(self)

        heading = QLabel("Receive")

        heading.setStyleSheet(
            "font-size: 26px; "
            "font-weight: 700; "
            "padding: 20px;"
        )

        layout.addWidget(heading)

        description = QLabel(
            "Manage WSP-1 Silent Payment receiving addresses. "
            "Labeled addresses remain under the same encrypted "
            "wallet identity."
        )

        description.setWordWrap(True)

        layout.addWidget(description)

        self.load_button = QPushButton(
            "Refresh receive addresses"
        )

        self.load_button.clicked.connect(
            self.load_addresses
        )

        layout.addWidget(
            self.load_button
        )

        label_heading = QLabel(
            "Create labeled address"
        )

        label_heading.setStyleSheet(
            "font-size: 18px; "
            "font-weight: 700; "
            "padding-top: 18px;"
        )

        layout.addWidget(label_heading)

        self.label_name = QLineEdit()

        self.label_name.setPlaceholderText(
            "Example: Invoice 001 / Customer A"
        )

        layout.addWidget(
            self.label_name
        )

        self.create_button = QPushButton(
            "Create new labeled address"
        )

        self.create_button.clicked.connect(
            self.create_label
        )

        layout.addWidget(
            self.create_button
        )

        self.table = QTableWidget(
            0,
            3,
        )

        self.table.setHorizontalHeaderLabels(
            [
                "Label",
                "Name",
                "Silent Payment Address",
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
            0,
            QHeaderView.ResizeToContents,
        )

        header.setSectionResizeMode(
            1,
            QHeaderView.ResizeToContents,
        )

        header.setSectionResizeMode(
            2,
            QHeaderView.Stretch,
        )

        self.table.itemSelectionChanged.connect(
            self._selection_changed
        )

        layout.addWidget(self.table)

        self.copy_button = QPushButton(
            "Copy selected address"
        )

        self.copy_button.setEnabled(
            False
        )

        self.copy_button.clicked.connect(
            self.copy_selected_address
        )

        layout.addWidget(
            self.copy_button
        )

        self.status = QLabel("")

        self.status.setWordWrap(True)

        layout.addWidget(self.status)

        warning = QLabel(
            "EXPERIMENTAL / REGTEST ONLY"
        )

        warning.setStyleSheet(
            "font-weight: 700; "
            "padding-top: 12px;"
        )

        layout.addWidget(warning)

    def _populate(
        self,
        addresses,
    ):
        self.table.setRowCount(
            len(addresses)
        )

        for row, item in enumerate(
            addresses
        ):
            label_text = (
                "Base"
                if item["label"] is None
                else str(item["label"])
            )

            values = [
                QTableWidgetItem(
                    label_text
                ),
                QTableWidgetItem(
                    item["name"]
                ),
                QTableWidgetItem(
                    item["address"]
                ),
            ]

            values[2].setData(
                Qt.UserRole,
                item["address"],
            )

            for column, value in enumerate(
                values
            ):
                self.table.setItem(
                    row,
                    column,
                    value,
                )

    def load_addresses(self):
        try:
            with (
                self.session_service
                .secret_lease()
            ) as secret:
                addresses = (
                    self.wallet_service
                    .receive_addresses(
                        secret
                    )
                )

            self._populate(
                addresses
            )

            self.status.setText(
                f"{len(addresses)} "
                "receive address(es) loaded."
            )

        except Exception:
            self.table.setRowCount(0)

            self.status.setText(
                "Unable to load wallet addresses."
            )

    def create_label(self):
        name = self.label_name.text()

        if not name.strip():
            self.status.setText(
                "Enter a label name."
            )
            return

        self.create_button.setEnabled(
            False
        )

        try:
            with (
                self.session_service
                .secret_lease()
            ) as secret:
                result = (
                    self.wallet_service
                    .create_labeled_address(
                        secret,
                        name,
                    )
                )

            self.label_name.clear()

            self.load_addresses()

            self.status.setText(
                "Created Label "
                f'{result["label"]}: '
                f'{result["name"]}. '
                "Run a wallet scan after adding "
                "new label metadata."
            )

        except Exception:
            self.status.setText(
                "Unable to create labeled address."
            )

        finally:
            self.create_button.setEnabled(
                True
            )

    def _selection_changed(self):
        self.copy_button.setEnabled(
            bool(
                self.table.selectedItems()
            )
        )

    def copy_selected_address(self):
        selected = (
            self.table
            .selectionModel()
            .selectedRows()
        )

        if not selected:
            return

        row = selected[0].row()

        item = self.table.item(
            row,
            2,
        )

        address = item.data(
            Qt.UserRole
        )

        QApplication.clipboard().setText(
            address
        )

        self.status.setText(
            "Silent Payment address copied."
        )
