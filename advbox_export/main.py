import sys
from pathlib import Path

from dotenv import load_dotenv
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from advbox_export.core.config import ConfigStore
from advbox_export.core.paths import config_file
from advbox_export.ui.main_window import MainWindow
from advbox_export.ui.theme import _RES_DIR, apply_theme

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")

    app = QApplication(sys.argv)
    app.setApplicationName("AdvBox Export")

    icon_path = _RES_DIR / "icons" / "app-icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    tema_inicial = ConfigStore(config_file()).load().theme
    apply_theme(app, theme=tema_inicial)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
