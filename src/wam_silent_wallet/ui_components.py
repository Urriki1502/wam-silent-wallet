from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class BrandMark(QLabel):
    def __init__(self, text="W", parent=None):
        super().__init__(text, parent)

        self.setAlignment(Qt.AlignCenter)

        self.setFixedSize(
            38,
            38,
        )

        self.setStyleSheet(
            """
            QLabel {
                background: #17191c;
                color: white;
                border-radius: 10px;
                font-size: 20px;
                font-weight: 800;
            }
            """
        )


class StatusBadge(QLabel):
    """
    Compact status badge.

    Kinds:
        neutral
        success
        warning
        danger
        info
    """

    COLORS = {
        "neutral": (
            "#eceef2",
            "#4b515b",
        ),
        "success": (
            "#e8f5ec",
            "#257942",
        ),
        "warning": (
            "#fff4dc",
            "#8a6100",
        ),
        "danger": (
            "#fdeaea",
            "#a73535",
        ),
        "info": (
            "#e9f0fb",
            "#315f9f",
        ),
    }

    def __init__(
        self,
        text="Unknown",
        kind="neutral",
        parent=None,
    ):
        super().__init__(parent)

        self.setAlignment(
            Qt.AlignCenter
        )

        self.setMinimumHeight(
            28
        )

        self.setContentsMargins(
            10,
            0,
            10,
            0,
        )

        self.set_status(
            text,
            kind,
        )

    def set_status(
        self,
        text,
        kind="neutral",
    ):
        background, foreground = (
            self.COLORS.get(
                kind,
                self.COLORS["neutral"],
            )
        )

        self.setText(text)

        self.setStyleSheet(
            f"""
            QLabel {{
                background: {background};
                color: {foreground};
                border-radius: 14px;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: 700;
            }}
            """
        )


class MetricCard(QFrame):
    def __init__(
        self,
        title,
        value="-",
        unit=None,
        subtitle=None,
        parent=None,
    ):
        super().__init__(parent)

        self.setObjectName(
            "MetricCard"
        )

        self.setMinimumHeight(
            135
        )

        self.setStyleSheet(
            """
            QFrame#MetricCard {
                background: white;
                border: 1px solid #e1e4e8;
                border-radius: 14px;
            }
            """
        )

        layout = QVBoxLayout(self)

        layout.setContentsMargins(
            18,
            16,
            18,
            16,
        )

        layout.setSpacing(
            6
        )

        self.title_label = QLabel(
            title.upper()
        )

        self.title_label.setStyleSheet(
            """
            QLabel {
                color: #737a86;
                font-size: 11px;
                font-weight: 700;
            }
            """
        )

        layout.addWidget(
            self.title_label
        )

        value_row = QHBoxLayout()

        value_row.setSpacing(
            7
        )

        self.value_label = QLabel(
            str(value)
        )

        self.value_label.setStyleSheet(
            """
            QLabel {
                color: #17191c;
                font-size: 27px;
                font-weight: 750;
            }
            """
        )

        value_row.addWidget(
            self.value_label
        )

        if unit:
            self.unit_label = QLabel(
                unit
            )

            self.unit_label.setAlignment(
                Qt.AlignBottom
                | Qt.AlignLeft
            )

            self.unit_label.setStyleSheet(
                """
                QLabel {
                    color: #6d7480;
                    font-size: 13px;
                    font-weight: 700;
                    padding-bottom: 4px;
                }
                """
            )

            value_row.addWidget(
                self.unit_label
            )

        value_row.addStretch()

        layout.addLayout(
            value_row
        )

        self.subtitle_label = QLabel(
            subtitle or ""
        )

        self.subtitle_label.setStyleSheet(
            """
            QLabel {
                color: #8a919c;
                font-size: 12px;
            }
            """
        )

        layout.addWidget(
            self.subtitle_label
        )

        layout.addStretch()

    def set_value(
        self,
        value,
    ):
        self.value_label.setText(
            str(value)
        )

    def set_subtitle(
        self,
        text,
    ):
        self.subtitle_label.setText(
            text
        )


class SectionHeading(QWidget):
    def __init__(
        self,
        title,
        subtitle=None,
        parent=None,
    ):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        layout.setSpacing(
            4
        )

        title_label = QLabel(
            title
        )

        title_label.setStyleSheet(
            """
            QLabel {
                font-size: 26px;
                font-weight: 750;
            }
            """
        )

        layout.addWidget(
            title_label
        )

        if subtitle:
            subtitle_label = QLabel(
                subtitle
            )

            subtitle_label.setWordWrap(
                True
            )

            subtitle_label.setStyleSheet(
                """
                QLabel {
                    color: #727984;
                    font-size: 13px;
                }
                """
            )

            layout.addWidget(
                subtitle_label
            )
