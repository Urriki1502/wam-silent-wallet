import sys

from PySide6.QtWidgets import QApplication

from wam_silent_wallet.main_window import MainWindow
from wam_silent_wallet.theme import APP_STYLE


def main():
    app = QApplication(sys.argv)

    app.setApplicationName(
        "WAM Silent Wallet"
    )

    app.setStyleSheet(
        APP_STYLE
    )

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
