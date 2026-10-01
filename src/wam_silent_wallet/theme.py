APP_STYLE = """
QMainWindow,
QWidget {
    background: #f6f7f9;
    color: #17191c;
    font-size: 14px;
}

QLabel {
    background: transparent;
}

QLineEdit {
    background: white;
    border: 1px solid #d8dce2;
    border-radius: 8px;
    padding: 9px 11px;
    min-height: 20px;
}

QLineEdit:focus {
    border: 1px solid #8f98a8;
}

QPushButton {
    background: #17191c;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 9px 14px;
    min-height: 20px;
    font-weight: 600;
}

QPushButton:hover {
    background: #2a2d32;
}

QPushButton:pressed {
    background: #0b0c0e;
}

QPushButton:disabled {
    background: #d8dce2;
    color: #8b919b;
}

QListWidget {
    background: #eceef2;
    border: none;
    border-radius: 10px;
    padding: 6px;
    outline: 0;
}

QListWidget::item {
    padding: 10px 12px;
    margin: 2px;
    border-radius: 7px;
}

QListWidget::item:selected {
    background: #17191c;
    color: white;
    font-weight: 600;
}

QListWidget::item:hover:!selected {
    background: #dde1e7;
}

QTableWidget {
    background: white;
    alternate-background-color: #f7f8fa;
    border: 1px solid #dde1e7;
    border-radius: 8px;
    gridline-color: #eceef2;
    selection-background-color: #dfe4eb;
    selection-color: #17191c;
}

QHeaderView::section {
    background: #eceef2;
    border: none;
    border-bottom: 1px solid #d8dce2;
    padding: 8px;
    font-weight: 700;
}

QMessageBox {
    background: #f6f7f9;
}
"""
