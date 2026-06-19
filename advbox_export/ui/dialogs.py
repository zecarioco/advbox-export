"""Helpers de UI compartilhados — dialogs padronizados.

Usados pra evitar os botões nativos genéricos "Yes/No" do Qt em vários
pontos do app. Tudo passa por um único QMessageBox customizado com
botões "Sim" (✓ verde) e "Não" (✗ outline), com ícones SVG coerentes
com o resto do app.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMessageBox, QPushButton, QWidget

from advbox_export.ui.theme import _RES_DIR


def confirmar(
    parent: QWidget | None,
    *,
    titulo: str,
    mensagem: str,
    theme: str = "light",
    padrao_sim: bool = False,
) -> bool:
    """QMessageBox de confirmação com botões 'Sim' (✓) e 'Não' (✗).

    `theme` define qual conjunto de ícones usar ("light"/"dark").
    `padrao_sim=False` (default) foca o botão Não — mais seguro pra ações
    destrutivas. Retorna True se o usuário confirmar.
    """
    box = QMessageBox(parent)
    box.setWindowTitle(titulo)
    box.setText(mensagem)
    box.setIcon(QMessageBox.Icon.Question)

    sufixo = "dark" if theme == "dark" else "light"
    icons_dir = _RES_DIR / "icons"
    icon_check = icons_dir / f"check-{sufixo}.svg"
    icon_x = icons_dir / f"x-{sufixo}.svg"

    btn_sim = QPushButton("Sim")
    if icon_check.exists():
        btn_sim.setIcon(QIcon(str(icon_check)))
    btn_sim.setCursor(Qt.CursorShape.PointingHandCursor)

    btn_nao = QPushButton("Não")
    if icon_x.exists():
        btn_nao.setIcon(QIcon(str(icon_x)))
    btn_nao.setProperty("variant", "outline")
    btn_nao.setCursor(Qt.CursorShape.PointingHandCursor)

    box.addButton(btn_sim, QMessageBox.ButtonRole.AcceptRole)
    box.addButton(btn_nao, QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(btn_sim if padrao_sim else btn_nao)

    box.exec()
    return box.clickedButton() is btn_sim
