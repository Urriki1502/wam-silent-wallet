from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..services.privacy_service import NetworkPrivacyService
from ..ui_components import SectionHeading, StatusBadge


class PrivacyPage(QWidget):
    def __init__(
        self,
        node_service,
        parent=None,
    ):
        super().__init__(parent)

        self.node_service = node_service
        self.privacy_service = (
            NetworkPrivacyService(
                node_service
            )
        )

        self._build()
        self.refresh()

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
            "Network Privacy",
            (
                "Audit how the local WAM Core node reaches the P2P network. "
                "Wallet RPC remains local; Tor/proxy policy belongs to WAM Core."
            ),
        )

        layout.addWidget(
            heading
        )

        self.mode_badge = StatusBadge(
            "CHECKING",
            "neutral",
        )

        layout.addWidget(
            self.mode_badge
        )

        grid = QGridLayout()

        grid.setHorizontalSpacing(
            28
        )

        grid.setVerticalSpacing(
            10
        )

        self.mode_value = QLabel("-")
        self.rpc_value = QLabel("-")
        self.cookie_value = QLabel("-")
        self.network_active_value = QLabel("-")
        self.onion_value = QLabel("-")
        self.onion_proxy_value = QLabel("-")
        self.ipv4_value = QLabel("-")
        self.ipv4_proxy_value = QLabel("-")
        self.ipv6_value = QLabel("-")
        self.ipv6_proxy_value = QLabel("-")
        self.clearnet_value = QLabel("-")

        rows = [
            ("Privacy mode", self.mode_value),
            ("RPC loopback", self.rpc_value),
            ("RPC cookie", self.cookie_value),
            ("Network active", self.network_active_value),
            ("Onion reachable", self.onion_value),
            ("Onion proxy", self.onion_proxy_value),
            ("IPv4 reachable", self.ipv4_value),
            ("IPv4 proxy", self.ipv4_proxy_value),
            ("IPv6 reachable", self.ipv6_value),
            ("IPv6 proxy", self.ipv6_proxy_value),
            ("Clearnet proxy-routed", self.clearnet_value),
        ]

        for row, (
            name,
            value,
        ) in enumerate(rows):
            label = QLabel(name)

            label.setStyleSheet(
                """
                QLabel {
                    color: #747b86;
                    font-weight: 600;
                }
                """
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

        layout.addLayout(
            grid
        )

        self.warning_text = QLabel(
            "-"
        )

        self.warning_text.setWordWrap(
            True
        )

        self.warning_text.setStyleSheet(
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
            self.warning_text
        )

        self.refresh_button = QPushButton(
            "Refresh Privacy Status"
        )

        self.refresh_button.clicked.connect(
            self.refresh
        )

        layout.addWidget(
            self.refresh_button
        )

        note = QLabel(
            "This page is read-only. It does not modify wam.conf, start Tor, "
            "or reroute traffic. A TOR READY status is shown only when WAM Core "
            "reports onion reachability through a proxy and no reachable "
            "clearnet network appears to bypass a proxy."
        )

        note.setWordWrap(
            True
        )

        note.setStyleSheet(
            """
            QLabel {
                color: #747b86;
                font-size: 12px;
            }
            """
        )

        layout.addWidget(
            note
        )

        layout.addStretch()

    def refresh(self):
        self.refresh_button.setEnabled(
            False
        )

        self.mode_badge.set_status(
            "CHECKING",
            "neutral",
        )

        try:
            result = (
                self.privacy_service
                .snapshot()
            )

            self.apply_snapshot(
                result
            )

        except Exception as exc:
            self.mode_badge.set_status(
                "UNAVAILABLE",
                "danger",
            )

            self.mode_value.setText(
                "Unavailable"
            )

            self.warning_text.setText(
                "Privacy inspection failed safely: "
                f"{type(exc).__name__}."
            )

        finally:
            self.refresh_button.setEnabled(
                True
            )

    def apply_snapshot(
        self,
        result,
    ):
        mode_labels = {
            "tor_ready": (
                "TOR READY",
                "success",
            ),
            "tor_available_mixed": (
                "TOR MIXED",
                "warning",
            ),
            "proxy_partial": (
                "PROXY PARTIAL",
                "warning",
            ),
            "direct": (
                "DIRECT",
                "warning",
            ),
        }

        badge_text, badge_kind = (
            mode_labels.get(
                result.mode,
                (
                    result.mode.upper(),
                    "neutral",
                ),
            )
        )

        self.mode_badge.set_status(
            badge_text,
            badge_kind,
        )

        self.mode_value.setText(
            result.mode
        )

        self.rpc_value.setText(
            "Local"
            if result.rpc_loopback
            else "Not local"
        )

        self.cookie_value.setText(
            "Available"
            if result.cookie_available
            else "Missing"
        )

        self.network_active_value.setText(
            str(result.network_active)
        )

        self.onion_value.setText(
            str(result.onion_reachable)
        )

        self.onion_proxy_value.setText(
            result.onion_proxy
            or "-"
        )

        self.ipv4_value.setText(
            str(result.ipv4_reachable)
        )

        self.ipv4_proxy_value.setText(
            result.ipv4_proxy
            or "-"
        )

        self.ipv6_value.setText(
            str(result.ipv6_reachable)
        )

        self.ipv6_proxy_value.setText(
            result.ipv6_proxy
            or "-"
        )

        self.clearnet_value.setText(
            str(
                result
                .clearnet_proxy_routed
            )
        )

        if result.warnings:
            self.warning_text.setText(
                "Warnings: "
                + ", ".join(
                    result.warnings
                )
            )
        else:
            self.warning_text.setText(
                "Warnings: NONE"
            )
