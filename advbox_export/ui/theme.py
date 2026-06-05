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
_FONTES_CARREGADAS = False


def apply_theme(app: QApplication, theme: str = "light") -> None:
    """Carrega fontes embarcadas e aplica o stylesheet do tema escolhido."""
    _carregar_fontes()
    qss_file = "styles_dark.qss" if theme == "dark" else "styles.qss"
    qss_path = _RES_DIR / qss_file
    if not qss_path.exists():
        qss_path = _RES_DIR / "styles.qss"
    qss = qss_path.read_text(encoding="utf-8")
    qss = _injetar_paths_de_icones(qss, theme=theme)
    app.setStyleSheet(qss)


def _injetar_paths_de_icones(qss: str, *, theme: str) -> str:
    """Substitui {{ICON_NOME}} pelos paths absolutos (sempre com '/').

    QSS aceita url() com path absoluto; usar placeholders evita ter que compilar
    qrc/resources e funciona igual em dev e empacotado.
    """
    sufixo = "dark" if theme == "dark" else "light"
    icons_dir = _RES_DIR / "icons"
    substituicoes = {
        "{{CHEVRON_DOWN}}": icons_dir / f"chevron-down-{sufixo}.svg",
        "{{CHEVRON_LEFT}}": icons_dir / f"chevron-left-{sufixo}.svg",
        "{{CHEVRON_RIGHT}}": icons_dir / f"chevron-right-{sufixo}.svg",
        "{{TRASH}}": icons_dir / f"trash-{sufixo}.svg",
    }
    for placeholder, path in substituicoes.items():
        qss = qss.replace(placeholder, str(path).replace("\\", "/"))
    return qss


def _carregar_fontes() -> None:
    global _FONTES_CARREGADAS
    if _FONTES_CARREGADAS or not _FONTS_DIR.exists():
        return
    for fonte in sorted(_FONTS_DIR.glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(fonte))
    _FONTES_CARREGADAS = True
