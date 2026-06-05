import sys
from pathlib import Path

from dotenv import load_dotenv
from PySide6.QtWidgets import QApplication
from qt_material import apply_stylesheet

from advbox_export.ui.main_window import MainWindow

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")

    app = QApplication(sys.argv)
    apply_stylesheet(app, theme="light_blue.xml")

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
