import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from wam_silent_wallet.main_window import MainWindow
from wam_silent_wallet.theme import APP_STYLE


def install_shutdown_signals(
    window,
):
    def request_shutdown(
        signum,
        frame,
    ):
        # Python signal handlers run on the main interpreter
        # thread.  Schedule the Qt close on the event queue so
        # normal closeEvent teardown remains the single authority.
        QTimer.singleShot(
            0,
            window.close,
        )

    for name in (
        "SIGINT",
        "SIGTERM",
    ):
        signum = getattr(
            signal,
            name,
            None,
        )

        if signum is not None:
            signal.signal(
                signum,
                request_shutdown,
            )

    return request_shutdown


def main():
    app = QApplication(sys.argv)

    app.setApplicationName(
        "WAM Silent Wallet"
    )

    app.setStyleSheet(
        APP_STYLE
    )

    window = MainWindow()

    install_shutdown_signals(
        window
    )

    app.aboutToQuit.connect(
        window.shutdown_for_application_exit
    )

    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
