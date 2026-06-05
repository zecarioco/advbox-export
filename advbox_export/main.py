import sys
from pathlib import Path

from dotenv import load_dotenv
from PySide6.QtWidgets import QApplication

from advbox_export.ui.main_window import MainWindow
from advbox_export.ui.theme import apply_theme

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")

    app = QApplication(sys.argv)
    app.setApplicationName("AdvBox Export")
    apply_theme(app)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
