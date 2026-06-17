"""Dialog pra escolher quais destinatários incluir no export.

A API da AdvBox não expõe grupos/equipes via /settings (campos disponíveis:
id, name, email, cellphone). Esse dialog é o substituto manual: usuário marca
quais nomes quer ver no XLSX. None = todos.
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


class UsersDialog(QDialog):
    def __init__(
        self,
        nomes_disponiveis: Iterable[str],
        nomes_selecionados: set[str] | None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Filtrar destinatários")
        self.resize(440, 560)

        nomes = sorted({n.strip() for n in nomes_disponiveis if n and n.strip()})
        self._nomes = nomes
        # None = "todos marcados" como estado inicial (sem filtro = inclui tudo)
        marcados = set(nomes) if nomes_selecionados is None else set(nomes_selecionados)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        info = QLabel(
            "Marque os destinatários que devem aparecer no export. "
            "Tarefas concluídas por outros usuários serão descartadas."
        )
        info.setWordWrap(True)
        info.setObjectName("mutedLabel")
        layout.addWidget(info)

        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Buscar…")
        self.busca.textChanged.connect(self._aplicar_busca)
        layout.addWidget(self.busca)

        atalhos = QHBoxLayout()
        btn_todos = QPushButton("Marcar todos")
        btn_todos.clicked.connect(lambda: self._marcar_visiveis(True))
        btn_nenhum = QPushButton("Desmarcar todos")
        btn_nenhum.clicked.connect(lambda: self._marcar_visiveis(False))
        atalhos.addWidget(btn_todos)
        atalhos.addWidget(btn_nenhum)
        atalhos.addStretch()
        layout.addLayout(atalhos)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        self._container_layout = QVBoxLayout(container)
        self._container_layout.setContentsMargins(4, 4, 4, 4)
        self._container_layout.setSpacing(4)

        self._checkboxes: dict[str, QCheckBox] = {}
        for nome in nomes:
            chk = QCheckBox(nome)
            chk.setChecked(nome in marcados)
            self._checkboxes[nome] = chk
            self._container_layout.addWidget(chk)
        self._container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("mutedLabel")
        layout.addWidget(self.lbl_status)
        self._atualizar_status()
        for chk in self._checkboxes.values():
            chk.toggled.connect(self._atualizar_status)

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
        self.lbl_status.setText(f"{n} de {total} selecionados")

    def selecionados(self) -> list[str]:
        return [nome for nome, c in self._checkboxes.items() if c.isChecked()]

    def todos_selecionados(self) -> bool:
        return all(c.isChecked() for c in self._checkboxes.values())
