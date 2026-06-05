from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication


def _resource_dir() -> Path:
    """Retorna o dir dos recursos da UI.

    Em dev (rodando do source), é o próprio __file__'s parent.
    Empacotado com PyInstaller, é sys._MEIPASS/advbox_export/ui (caminho
    declarado nos --add-data do workflow).
    """
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "advbox_export" / "ui"
    return Path(__file__).resolve().parent


_RES_DIR = _resource_dir()
_FONTS_DIR = _RES_DIR / "fonts"
_QSS_PATH = _RES_DIR / "styles.qss"


def apply_theme(app: QApplication) -> None:
    """Carrega fontes embarcadas e aplica o stylesheet sage green warm."""
    _carregar_fontes()
    qss = _QSS_PATH.read_text(encoding="utf-8")
    app.setStyleSheet(qss)


def _carregar_fontes() -> None:
    if not _FONTS_DIR.exists():
        return
    for fonte in sorted(_FONTS_DIR.glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(fonte))
