from PySide6.QtCore import Signal

from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..ui_components import SectionHeading


class SettingsPage(QWidget):
    settings_saved = Signal(object)

    def __init__(
        self,
        config_service,
        runtime_config,
        parent=None,
    ):
        super().__init__(parent)

        self.config_service = config_service
        self.runtime_config = runtime_config

        self._build()
        self.load_config(
            runtime_config
        )

    def _build(self):
        layout = QVBoxLayout(self)

        layout.setContentsMargins(
            24,
            18,
            24,
            24,
        )

        layout.setSpacing(
            16
        )

        heading = SectionHeading(
            "Settings",
            (
                "Runtime settings for the local WAM regtest node, "
                "background sync and transaction fee policy."
            ),
        )

        layout.addWidget(
            heading
        )

        form = QFormLayout()

        form.setHorizontalSpacing(
            24
        )

        form.setVerticalSpacing(
            12
        )

        self.network_value = QLabel(
            "regtest"
        )

        self.network_value.setStyleSheet(
            "font-weight: 700;"
        )

        form.addRow(
            "Network",
            self.network_value,
        )

        self.rpc_url = QLineEdit()

        self.rpc_url.setPlaceholderText(
            "http://127.0.0.1:18443"
        )

        form.addRow(
            "RPC URL",
            self.rpc_url,
        )

        self.cookie_path = QLineEdit()

        form.addRow(
            "RPC cookie",
            self.cookie_path,
        )

        self.sync_interval = (
            QDoubleSpinBox()
        )

        self.sync_interval.setRange(
            2.0,
            300.0,
        )

        self.sync_interval.setDecimals(
            1
        )

        self.sync_interval.setSingleStep(
            1.0
        )

        self.sync_interval.setSuffix(
            " s"
        )

        form.addRow(
            "Background sync",
            self.sync_interval,
        )

        self.fee_tier = QComboBox()

        self.fee_tier.addItems(
            [
                "Economy",
                "Normal",
                "Priority",
            ]
        )

        form.addRow(
            "Default fee tier",
            self.fee_tier,
        )

        layout.addLayout(
            form
        )

        note = QLabel(
            "REGTEST ONLY. RPC must remain local at 127.0.0.1. "
            "Fee tier and sync interval apply immediately after Save. "
            "RPC URL or cookie-path changes are saved safely and require "
            "an application restart before the node connection is rebuilt."
        )

        note.setWordWrap(
            True
        )

        note.setStyleSheet(
            """
            QLabel {
                color: #747b86;
                padding: 10px;
                border: 1px solid #e1e4e8;
                border-radius: 8px;
            }
            """
        )

        layout.addWidget(
            note
        )

        buttons = QHBoxLayout()

        self.reset_button = QPushButton(
            "Load Safe Defaults"
        )

        self.reset_button.clicked.connect(
            self.load_defaults
        )

        buttons.addWidget(
            self.reset_button
        )

        self.save_button = QPushButton(
            "Save Settings"
        )

        self.save_button.clicked.connect(
            self.save_settings
        )

        buttons.addWidget(
            self.save_button
        )

        layout.addLayout(
            buttons
        )

        self.status = QLabel(
            "No settings changes."
        )

        self.status.setWordWrap(
            True
        )

        layout.addWidget(
            self.status
        )

        layout.addStretch()

    def load_config(
        self,
        config,
    ):
        self.runtime_config = config

        self.network_value.setText(
            config.network
        )

        self.rpc_url.setText(
            config.rpc_url
        )

        self.cookie_path.setText(
            config.cookie_path
        )

        self.sync_interval.setValue(
            config.sync_interval_seconds
        )

        self.fee_tier.setCurrentText(
            config.fee_tier
        )

    def load_defaults(self):
        defaults = (
            self.config_service
            .defaults()
        )

        self.network_value.setText(
            defaults.network
        )

        self.rpc_url.setText(
            defaults.rpc_url
        )

        self.cookie_path.setText(
            defaults.cookie_path
        )

        self.sync_interval.setValue(
            defaults.sync_interval_seconds
        )

        self.fee_tier.setCurrentText(
            defaults.fee_tier
        )

        self.status.setText(
            "Safe defaults loaded into the form. "
            "Press Save Settings to persist them."
        )

    def save_settings(self):
        old_config = self.runtime_config

        try:
            saved = (
                self.config_service
                .save(
                    {
                        "version": 1,
                        "network": "regtest",
                        "rpc_url": (
                            self.rpc_url
                            .text()
                            .strip()
                        ),
                        "cookie_path": (
                            self.cookie_path
                            .text()
                            .strip()
                        ),
                        "sync_interval_seconds": (
                            self.sync_interval
                            .value()
                        ),
                        "fee_tier": (
                            self.fee_tier
                            .currentText()
                        ),
                    }
                )
            )

        except ValueError as exc:
            self.status.setText(
                "Settings rejected safely: "
                f"{exc}."
            )

            return

        self.runtime_config = saved

        restart_required = (
            saved.rpc_url
            != old_config.rpc_url
            or saved.cookie_path
            != old_config.cookie_path
        )

        self.settings_saved.emit(
            saved
        )

        if restart_required:
            self.status.setText(
                "Settings saved. Fee tier and sync interval are active now. "
                "Restart the application to apply the RPC endpoint/cookie change."
            )

        else:
            self.status.setText(
                "Settings saved and active."
            )
