from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow, QVBoxLayout, QWidget


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AdvBox Export")
        self.resize(960, 640)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        placeholder = QLabel("AdvBox Export — scaffold pronto")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(placeholder)

        self.setCentralWidget(central)
