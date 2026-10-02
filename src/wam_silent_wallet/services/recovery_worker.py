"""Dedicated recovery thread.

The worker stores its final result/error on the QThread object itself.
The GUI consumes that state from QThread.finished, avoiding custom
cross-thread result-signal lifecycle ambiguity.
"""

from __future__ import annotations

from PySide6.QtCore import QThread


class RecoveryRestoreThread(QThread):
    def __init__(
        self,
        wallet_service,
        backup_path: str,
        secret,
        parent=None,
    ):
        super().__init__(parent)

        self.wallet_service = wallet_service
        self.backup_path = backup_path

        self._secret = bytearray(
            secret
        )

        self.result = None
        self.error_type = None
        self.error_code = None

    def run(self):
        try:
            self.result = (
                self.wallet_service
                .restore_recovery_bundle(
                    self._secret,
                    self.backup_path,
                )
            )

        except Exception as exc:
            self.error_type = (
                type(exc).__name__
            )

            self.error_code = str(
                exc
            )

        finally:
            for index in range(
                len(self._secret)
            ):
                self._secret[index] = 0
