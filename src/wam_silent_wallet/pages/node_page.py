from datetime import datetime

from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class NodePage(QWidget):
    def __init__(
        self,
        node_service,
        parent=None,
    ):
        super().__init__(parent)

        self.node_service = node_service

        self._build()

        self.refresh()

    def _build(self):
        layout = QVBoxLayout(self)

        heading = QLabel("Node")
        heading.setStyleSheet(
            "font-size: 26px; "
            "font-weight: 700; "
            "padding: 20px;"
        )

        layout.addWidget(heading)

        description = QLabel(
            "Status of the isolated WAM Core node used by "
            "this experimental Silent Payments wallet."
        )

        description.setWordWrap(True)

        layout.addWidget(description)

        grid = QGridLayout()

        self.state_value = QLabel("-")
        self.network_value = QLabel("-")
        self.blocks_value = QLabel("-")
        self.headers_value = QLabel("-")
        self.ibd_value = QLabel("-")
        self.mempool_value = QLabel("-")
        self.tip_tx_value = QLabel("-")
        self.tip_time_value = QLabel("-")
        self.tip_value = QLabel("-")
        self.rpc_value = QLabel("-")
        self.cookie_value = QLabel("-")

        rows = [
            ("Status", self.state_value),
            ("Network", self.network_value),
            ("Blocks", self.blocks_value),
            ("Headers", self.headers_value),
            ("Initial download", self.ibd_value),
            ("Mempool transactions", self.mempool_value),
            ("Tip transactions", self.tip_tx_value),
            ("Tip time", self.tip_time_value),
            ("Chain tip", self.tip_value),
            ("RPC", self.rpc_value),
            ("RPC cookie", self.cookie_value),
        ]

        for row, (name, value) in enumerate(rows):
            label = QLabel(name)

            label.setStyleSheet(
                "font-weight: 700;"
            )

            grid.addWidget(
                label,
                row,
                0,
            )

            grid.addWidget(
                value,
                row,
                1,
            )

        layout.addLayout(grid)

        self.refresh_button = QPushButton(
            "Refresh node"
        )

        self.refresh_button.clicked.connect(
            self.refresh
        )

        layout.addWidget(
            self.refresh_button
        )

        self.message = QLabel("")
        self.message.setWordWrap(True)

        layout.addWidget(
            self.message
        )

        layout.addStretch()

    def apply_snapshot(
        self,
        info: dict,
        *,
        automatic: bool = True,
    ):
        self.state_value.setText(
            "Connected / Ready"
            if info["ready"]
            else "Connected / Not ready"
        )

        self.network_value.setText(
            info["network"]
        )

        self.blocks_value.setText(
            str(info["blocks"])
        )

        self.headers_value.setText(
            str(info["headers"])
        )

        self.ibd_value.setText(
            str(info["ibd"])
        )

        self.mempool_value.setText(
            str(
                info.get(
                    "mempool_transactions",
                    "-",
                )
            )
        )

        self.tip_tx_value.setText(
            str(
                info.get(
                    "tip_tx_count",
                    "-",
                )
            )
        )

        tip_time = info.get(
            "tip_time"
        )

        if isinstance(
            tip_time,
            int,
        ):
            text = datetime.fromtimestamp(
                tip_time
            ).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        else:
            text = "-"

        self.tip_time_value.setText(
            text
        )

        self.tip_value.setText(
            info["tip"]
        )

        self.tip_value.setWordWrap(
            True
        )

        self.rpc_value.setText(
            info.get(
                "rpc_url",
                "-",
            )
        )

        cookie = info.get(
            "cookie_exists"
        )

        self.cookie_value.setText(
            "Available"
            if cookie is True
            else "Missing"
            if cookie is False
            else "-"
        )

        self.message.setText(
            "Node status auto-synchronized."
            if automatic
            else "WAM node status refreshed successfully."
        )

    def refresh(self):
        self.refresh_button.setEnabled(False)

        try:
            info = self.node_service.details()

            self.apply_snapshot(
                info,
                automatic=False,
            )

        except Exception:
            self.state_value.setText(
                "Disconnected"
            )

            for widget in [
                self.network_value,
                self.blocks_value,
                self.headers_value,
                self.ibd_value,
                self.mempool_value,
                self.tip_tx_value,
                self.tip_time_value,
                self.tip_value,
                self.rpc_value,
                self.cookie_value,
            ]:
                widget.setText("-")

            self.message.setText(
                "Unable to read WAM node status."
            )

        finally:
            self.refresh_button.setEnabled(True)
