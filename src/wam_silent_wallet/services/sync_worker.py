"""Qt background thread for periodic WAM wallet synchronization."""

import threading

from PySide6.QtCore import QThread, Signal


class BackgroundSyncThread(QThread):
    """Run sync cycles outside the GUI thread."""

    outcome = Signal(object)

    def __init__(
        self,
        sync_service,
        session_service,
        parent=None,
    ):
        super().__init__(parent)

        self.sync_service = sync_service
        self.session_service = session_service

        self._stop_event = threading.Event()
        self._wake_event = threading.Event()

    def stop(self):
        self._stop_event.set()
        self._wake_event.set()

    def request_sync(self):
        self._wake_event.set()

    def run(self):
        delay = 0.0

        while not self._stop_event.is_set():
            if delay > 0:
                self._wake_event.wait(delay)
                self._wake_event.clear()

                if self._stop_event.is_set():
                    break

            try:
                with (
                    self.session_service
                    .secret_lease()
                ) as secret:
                    result = (
                        self.sync_service
                        .cycle(secret)
                    )
            except Exception:
                break

            self.outcome.emit(
                result
            )

            try:
                delay = max(
                    0.25,
                    float(
                        result.next_delay_seconds
                    ),
                )
            except Exception:
                delay = 2.0
