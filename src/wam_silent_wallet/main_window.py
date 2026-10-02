from PySide6.QtCore import Qt

from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .services.node_service import NodeService
from .services.wallet_service import WalletService
from .services.session_service import SessionService
from .services.sync_service import BackgroundSyncService
from .services.sync_worker import BackgroundSyncThread

from .pages.lock_page import LockPage
from .pages.receive_page import ReceivePage
from .pages.send_page import SendPage
from .pages.payments_page import PaymentsPage
from .pages.node_page import NodePage
from .pages.backup_page import BackupPage

from .ui_components import (
    BrandMark,
    MetricCard,
    SectionHeading,
    StatusBadge,
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(
            "WAM Silent Wallet v0.1"
        )

        self.resize(
            1100,
            700,
        )

        self.node_service = (
            NodeService()
        )

        self.wallet_service = (
            WalletService()
        )

        self.session_service = (
            SessionService(
                self.wallet_service
            )
        )

        self.background_sync_service = (
            BackgroundSyncService(
                self.wallet_service,
                self.node_service,
            )
        )

        self.background_sync_thread = None
        self.payments_page = None
        self.node_page = None

        self.root_stack = (
            QStackedWidget()
        )

        self.lock_page = LockPage(
            self.session_service
        )

        self.lock_page.unlocked.connect(
            self._session_unlocked
        )

        self.root_stack.addWidget(
            self.lock_page
        )

        self.wallet_shell = None

        self.setCentralWidget(
            self.root_stack
        )

        self.root_stack.setCurrentWidget(
            self.lock_page
        )

    # ==========================================================
    # Session lifecycle
    # ==========================================================

    def _session_unlocked(self):
        if not self.session_service.unlocked:
            return

        self._destroy_wallet_shell()

        self.wallet_shell = (
            self._build_wallet_shell()
        )

        self.root_stack.addWidget(
            self.wallet_shell
        )

        self.root_stack.setCurrentWidget(
            self.wallet_shell
        )

        self._start_background_sync()

    def lock_wallet(self):
        self._stop_background_sync()

        self.session_service.lock()

        self._destroy_wallet_shell()

        self.lock_page.reset()

        self.root_stack.setCurrentWidget(
            self.lock_page
        )

    def _destroy_wallet_shell(self):
        if self.wallet_shell is None:
            return

        self.root_stack.removeWidget(
            self.wallet_shell
        )

        self.wallet_shell.deleteLater()

        self.wallet_shell = None
        self.payments_page = None
        self.node_page = None

    def closeEvent(self, event):
        self._stop_background_sync()

        self.session_service.lock()

        super().closeEvent(event)

    # ==========================================================
    # Background synchronization
    # ==========================================================

    def _start_background_sync(self):
        self._stop_background_sync()

        self.background_sync_service.reset()

        worker = BackgroundSyncThread(
            self.background_sync_service,
            self.session_service,
            self,
        )

        worker.outcome.connect(
            self._background_sync_outcome
        )

        self.background_sync_thread = worker

        self.scan_state.setText(
            "Auto sync starting..."
        )

        self.scan_badge.set_status(
            "AUTO SYNC",
            "info",
        )

        worker.start()

    def _stop_background_sync(self):
        worker = self.background_sync_thread

        if worker is None:
            return

        worker.stop()

        # Join before SessionService clears the unlock secret.
        worker.wait()

        self.background_sync_thread = None

    def _background_sync_outcome(
        self,
        outcome,
    ):
        if (
            self.wallet_shell is None
            or not self.session_service.unlocked
        ):
            return

        if outcome.node is not None:
            self._apply_dashboard_node_snapshot(
                outcome.node
            )

            if self.node_page is not None:
                self.node_page.apply_snapshot(
                    outcome.node,
                    automatic=True,
                )

        if outcome.status == "synced":
            result = outcome.wallet

            self._apply_dashboard_wallet_snapshot(
                result,
                automatic=True,
            )

            if self.payments_page is not None:
                self.payments_page.apply_snapshot(
                    result,
                    automatic=True,
                )

            return

        if outcome.status == "scanner_busy":
            self.scan_state.setText(
                "Scanner busy"
            )

            self.scan_badge.set_status(
                "BUSY",
                "info",
            )

            self.scan_message.setText(
                "Another wallet operation is using the scanner. "
                "Background sync will retry automatically."
            )

            return

        if outcome.status in (
            "node_not_ready",
            "node_error",
        ):
            self.scan_state.setText(
                "Waiting for node"
            )

            self.scan_badge.set_status(
                "WAITING",
                "warning",
            )

            self.scan_message.setText(
                "Background sync is waiting for WAM Core. "
                f"Retry in {outcome.next_delay_seconds:.0f}s."
            )

            return

        if outcome.status == "wallet_error":
            self.scan_state.setText(
                "Sync retry"
            )

            self.scan_badge.set_status(
                "RETRYING",
                "warning",
            )

            self.scan_message.setText(
                "Background wallet synchronization failed safely. "
                f"Retry in {outcome.next_delay_seconds:.0f}s "
                f"({outcome.error_code})."
            )

    def _apply_dashboard_node_snapshot(
        self,
        status: dict,
    ):
        self.node_state.setText(
            "Connected / Ready"
            if status["ready"]
            else "Connected / Not ready"
        )

        if status["ready"]:
            self.node_badge.set_status(
                "READY",
                "success",
            )

            self.header_node_badge.set_status(
                "NODE READY",
                "success",
            )

        else:
            self.node_badge.set_status(
                "NOT READY",
                "warning",
            )

            self.header_node_badge.set_status(
                "NODE NOT READY",
                "warning",
            )

        self.network_value.setText(
            status["network"]
        )

        self.blocks_value.setText(
            str(status["blocks"])
        )

        self.headers_value.setText(
            str(status["headers"])
        )

        self.ibd_value.setText(
            str(status["ibd"])
        )

        self.tip_value.setText(
            status["tip"][:24]
            + "..."
        )

    def _apply_dashboard_wallet_snapshot(
        self,
        result: dict,
        *,
        automatic: bool,
    ):
        confirmed = (
            result["confirmed_atoms"]
            / 100_000_000
        )

        available = (
            result["available_atoms"]
            / 100_000_000
        )

        pending_atoms = (
            result["unconfirmed_atoms"]
            or 0
        )

        pending = (
            pending_atoms
            / 100_000_000
        )

        self.scan_state.setText(
            "Auto synced"
            if automatic
            else "Synced"
        )

        self.scan_badge.set_status(
            "AUTO SYNC"
            if automatic
            else "SYNCED",
            "success",
        )

        self.balance_value.setText(
            f"{confirmed:.8f}"
        )

        self.available_value.setText(
            f"{available:.8f}"
        )

        self.pending_value.setText(
            f"{pending:.8f} WAM"
        )

        count = result.get(
            "payments_count"
        )

        if count is None:
            count = result.get(
                "payments",
                0,
            )

        self.payment_count.setText(
            str(count)
        )

        self.scan_message.setText(
            (
                "Background sync complete — "
                if automatic
                else "Scan complete — "
            )
            + f'{result["scan_blocks"]} '
            + "new block(s), "
            + f'{result["scan_transactions"]} '
            + "transaction(s), "
            + f'{result["scan_rollback"]} '
            + "rollback(s)."
        )

    # ==========================================================
    # Wallet shell
    # ==========================================================

    def _build_wallet_shell(self):
        root = QWidget()

        root_layout = QVBoxLayout(
            root
        )

        # ------------------------------------------------------
        # Header
        # ------------------------------------------------------

        header = QHBoxLayout()

        header.setContentsMargins(
            4,
            4,
            4,
            8,
        )

        header.setSpacing(
            12
        )

        brand = BrandMark(
            "W"
        )

        header.addWidget(
            brand
        )

        brand_text = QVBoxLayout()

        brand_text.setSpacing(
            0
        )

        app_name = QLabel(
            "WAM Silent Wallet"
        )

        app_name.setStyleSheet(
            """
            QLabel {
                font-size: 17px;
                font-weight: 750;
            }
            """
        )

        app_version = QLabel(
            "Desktop Preview · v0.1"
        )

        app_version.setStyleSheet(
            """
            QLabel {
                color: #7b828e;
                font-size: 11px;
            }
            """
        )

        brand_text.addWidget(
            app_name
        )

        brand_text.addWidget(
            app_version
        )

        header.addLayout(
            brand_text
        )

        header.addStretch()

        environment_badge = StatusBadge(
            "REGTEST",
            "warning",
        )

        header.addWidget(
            environment_badge
        )

        self.header_node_badge = (
            StatusBadge(
                "NODE CHECKING",
                "neutral",
            )
        )

        header.addWidget(
            self.header_node_badge
        )

        lock_button = QPushButton(
            "Lock Wallet"
        )

        lock_button.setFixedWidth(
            120
        )

        lock_button.clicked.connect(
            self.lock_wallet
        )

        header.addWidget(
            lock_button
        )

        root_layout.addLayout(
            header
        )

        # ------------------------------------------------------
        # Main body
        # ------------------------------------------------------

        body = QHBoxLayout()

        sidebar = QListWidget()

        sidebar.addItems(
            [
                "Dashboard",
                "Receive",
                "Send",
                "Payments",
                "Node",
                "Backup",
            ]
        )

        sidebar.setFixedWidth(
            180
        )

        pages = QStackedWidget()

        pages.addWidget(
            self._build_dashboard()
        )

        pages.addWidget(
            ReceivePage(
                self.wallet_service,
                self.session_service,
            )
        )

        pages.addWidget(
            SendPage(
                self.wallet_service,
                self.node_service,
                self.session_service,
            )
        )

        self.payments_page = PaymentsPage(
            self.wallet_service,
            self.node_service,
            self.session_service,
        )

        pages.addWidget(
            self.payments_page
        )

        self.node_page = NodePage(
            self.node_service
        )

        pages.addWidget(
            self.node_page
        )

        pages.addWidget(
            BackupPage(
                self.wallet_service,
                self.session_service,
            )
        )

        sidebar.currentRowChanged.connect(
            pages.setCurrentIndex
        )

        sidebar.setCurrentRow(0)

        body.addWidget(
            sidebar
        )

        body.addWidget(
            pages,
            1,
        )

        root_layout.addLayout(
            body
        )

        return root

    # ==========================================================
    # Dashboard
    # ==========================================================

    def _build_dashboard(self):
        page = QWidget()

        layout = QVBoxLayout(
            page
        )

        layout.setContentsMargins(
            24,
            18,
            24,
            24,
        )

        layout.setSpacing(
            18
        )

        # ------------------------------------------------------
        # Page heading
        # ------------------------------------------------------

        heading_row = QHBoxLayout()

        heading = SectionHeading(
            "Dashboard",
            (
                "Local WSP-1 wallet state and "
                "WAM regtest node overview."
            ),
        )

        heading_row.addWidget(
            heading
        )

        heading_row.addStretch()

        self.dashboard_status = (
            StatusBadge(
                "WALLET UNLOCKED",
                "success",
            )
        )

        heading_row.addWidget(
            self.dashboard_status
        )

        layout.addLayout(
            heading_row
        )

        # ------------------------------------------------------
        # Metric cards
        # ------------------------------------------------------

        cards = QHBoxLayout()

        cards.setSpacing(
            14
        )

        self.balance_card = MetricCard(
            "Confirmed balance",
            "-",
            "WAM",
            "Confirmed Silent Payments",
        )

        self.available_card = MetricCard(
            "Available",
            "-",
            "WAM",
            "Spendable balance",
        )

        self.payments_card = MetricCard(
            "Payments",
            "-",
            None,
            "Detected incoming payments",
        )

        cards.addWidget(
            self.balance_card
        )

        cards.addWidget(
            self.available_card
        )

        cards.addWidget(
            self.payments_card
        )

        layout.addLayout(
            cards
        )

        # Keep compatibility with current scan code.
        self.balance_value = (
            self.balance_card.value_label
        )

        self.available_value = (
            self.available_card.value_label
        )

        self.payment_count = (
            self.payments_card.value_label
        )

        # ------------------------------------------------------
        # Node status panel
        # ------------------------------------------------------

        node_panel = QWidget()

        node_panel.setStyleSheet(
            """
            QWidget#NodePanel {
                background: white;
                border: 1px solid #e1e4e8;
                border-radius: 14px;
            }
            """
        )

        node_panel.setObjectName(
            "NodePanel"
        )

        node_layout = QVBoxLayout(
            node_panel
        )

        node_layout.setContentsMargins(
            18,
            16,
            18,
            16,
        )

        node_top = QHBoxLayout()

        node_title = QLabel(
            "WAM Node"
        )

        node_title.setStyleSheet(
            """
            QLabel {
                font-size: 17px;
                font-weight: 750;
            }
            """
        )

        node_top.addWidget(
            node_title
        )

        node_top.addStretch()

        self.node_badge = (
            StatusBadge(
                "CHECKING",
                "neutral",
            )
        )

        node_top.addWidget(
            self.node_badge
        )

        node_layout.addLayout(
            node_top
        )

        grid = QGridLayout()

        grid.setHorizontalSpacing(
            30
        )

        grid.setVerticalSpacing(
            9
        )

        self.node_state = QLabel("-")
        self.network_value = QLabel("-")
        self.blocks_value = QLabel("-")
        self.headers_value = QLabel("-")
        self.ibd_value = QLabel("-")
        self.tip_value = QLabel("-")

        node_rows = [
            ("State", self.node_state),
            ("Network", self.network_value),
            ("Blocks", self.blocks_value),
            ("Headers", self.headers_value),
            ("Initial download", self.ibd_value),
            ("Chain tip", self.tip_value),
        ]

        for row, (name, value) in enumerate(
            node_rows
        ):
            label = QLabel(
                name
            )

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

        node_layout.addLayout(
            grid
        )

        refresh_node = QPushButton(
            "Refresh Node"
        )

        refresh_node.clicked.connect(
            self.refresh_node_status
        )

        node_layout.addWidget(
            refresh_node
        )

        layout.addWidget(
            node_panel
        )

        # ------------------------------------------------------
        # Scanner
        # ------------------------------------------------------

        scanner_panel = QWidget()

        scanner_panel.setObjectName(
            "ScannerPanel"
        )

        scanner_panel.setStyleSheet(
            """
            QWidget#ScannerPanel {
                background: white;
                border: 1px solid #e1e4e8;
                border-radius: 14px;
            }
            """
        )

        scanner_layout = QVBoxLayout(
            scanner_panel
        )

        scanner_layout.setContentsMargins(
            18,
            16,
            18,
            16,
        )

        scanner_top = QHBoxLayout()

        scanner_title = QLabel(
            "Silent Wallet Scanner"
        )

        scanner_title.setStyleSheet(
            """
            QLabel {
                font-size: 17px;
                font-weight: 750;
            }
            """
        )

        scanner_top.addWidget(
            scanner_title
        )

        scanner_top.addStretch()

        self.scan_badge = (
            StatusBadge(
                "NOT SCANNED",
                "neutral",
            )
        )

        scanner_top.addWidget(
            self.scan_badge
        )

        scanner_layout.addLayout(
            scanner_top
        )

        scanner_grid = QGridLayout()

        self.scan_state = QLabel(
            "Not scanned"
        )

        self.pending_value = QLabel(
            "-"
        )

        scanner_rows = [
            (
                "Scanner",
                self.scan_state,
            ),
            (
                "Pending",
                self.pending_value,
            ),
        ]

        for row, (name, value) in enumerate(
            scanner_rows
        ):
            label = QLabel(name)

            label.setStyleSheet(
                """
                QLabel {
                    color: #747b86;
                    font-weight: 600;
                }
                """
            )

            scanner_grid.addWidget(
                label,
                row,
                0,
            )

            scanner_grid.addWidget(
                value,
                row,
                1,
            )

        scanner_layout.addLayout(
            scanner_grid
        )

        scan_button = QPushButton(
            "Scan Silent Wallet"
        )

        scan_button.clicked.connect(
            self.scan_wallet
        )

        scanner_layout.addWidget(
            scan_button
        )

        self.scan_message = QLabel(
            "Wallet has not been scanned in this session."
        )

        self.scan_message.setWordWrap(
            True
        )

        self.scan_message.setStyleSheet(
            """
            QLabel {
                color: #747b86;
                font-size: 12px;
            }
            """
        )

        scanner_layout.addWidget(
            self.scan_message
        )

        layout.addWidget(
            scanner_panel
        )

        layout.addStretch()

        self.refresh_node_status()

        return page

    def refresh_node_status(self):
        try:
            status = (
                self.node_service
                .snapshot()
            )

            self._apply_dashboard_node_snapshot(
                status
            )

        except Exception:
            self.node_state.setText(
                "Disconnected"
            )

            self.node_badge.set_status(
                "OFFLINE",
                "danger",
            )

            self.header_node_badge.set_status(
                "NODE OFFLINE",
                "danger",
            )

            for value in [
                self.network_value,
                self.blocks_value,
                self.headers_value,
                self.ibd_value,
                self.tip_value,
            ]:
                value.setText("-")

    def scan_wallet(self):
        self.scan_state.setText(
            "Scanning..."
        )

        self.scan_badge.set_status(
            "SCANNING",
            "info",
        )

        self.scan_message.setText(
            "Reading WAM regtest blockchain..."
        )

        QApplication.processEvents()

        try:
            result = (
                self.wallet_service
                .scan_snapshot(
                    self.session_service
                    .passphrase(),
                    self.node_service
                    .scanner_chain(),
                )
            )

            self._apply_dashboard_wallet_snapshot(
                {
                    **result,
                    "payments_count": result["payments"],
                },
                automatic=False,
            )

        except Exception:
            self.scan_state.setText(
                "Scan failed"
            )

            self.scan_badge.set_status(
                "FAILED",
                "danger",
            )

            self.scan_message.setText(
                "Unable to scan wallet."
            )
