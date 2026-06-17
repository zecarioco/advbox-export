"""Dialog pra editar quem está num grupo específico.

Lista os 51 usuários da AdvBox com checkboxes; mantém só os marcados como
membros do grupo. Busca textual no topo, atalhos 'marcar/desmarcar todos'.
"""
from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class MembrosDialog(QDialog):
    def __init__(
        self,
        grupo: str,
        nomes_disponiveis: Iterable[str],
        marcados_iniciais: Iterable[str],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Membros — {grupo}")
        self.resize(440, 600)

        nomes = sorted({n.strip() for n in nomes_disponiveis if n and n.strip()})
        marcados = set(marcados_iniciais)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        titulo = QLabel(grupo)
        f = titulo.font()
        f.setPointSize(14)
        f.setBold(True)
        titulo.setFont(f)
        layout.addWidget(titulo)

        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Buscar…")
        self.busca.textChanged.connect(self._aplicar_busca)
        layout.addWidget(self.busca)

        atalhos = QHBoxLayout()
        btn_todos = QPushButton("Marcar todos")
        btn_todos.clicked.connect(lambda: self._marcar_visiveis(True))
        btn_nenhum = QPushButton("Desmarcar todos")
        btn_nenhum.clicked.connect(lambda: self._marcar_visiveis(False))
        for b in (btn_todos, btn_nenhum):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            atalhos.addWidget(b)
        atalhos.addStretch()
        layout.addLayout(atalhos)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        cl = QVBoxLayout(container)
        cl.setContentsMargins(4, 4, 4, 4)
        cl.setSpacing(2)
        self._checkboxes: dict[str, QCheckBox] = {}
        for nome in nomes:
            chk = QCheckBox(nome)
            chk.setChecked(nome in marcados)
            chk.toggled.connect(self._atualizar_status)
            self._checkboxes[nome] = chk
            cl.addWidget(chk)
        cl.addStretch(1)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("mutedLabel")
        layout.addWidget(self.lbl_status)
        self._atualizar_status()

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def _aplicar_busca(self, texto: str) -> None:
        q = texto.strip().lower()
        for nome, chk in self._checkboxes.items():
            chk.setVisible(q in nome.lower() if q else True)

    def _marcar_visiveis(self, valor: bool) -> None:
        for chk in self._checkboxes.values():
            if chk.isVisible():
                chk.setChecked(valor)

    def _atualizar_status(self) -> None:
        n = sum(1 for c in self._checkboxes.values() if c.isChecked())
        total = len(self._checkboxes)
        self.lbl_status.setText(f"{n} de {total} marcados")

    def selecionados(self) -> list[str]:
        return [nome for nome, c in self._checkboxes.items() if c.isChecked()]
