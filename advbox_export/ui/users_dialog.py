"""Dialog de seleção de destinatários do próximo export.

Mostra duas seções: grupos cadastrados (com contagem de membros) e pessoas
avulsas (todos os 51 users da AdvBox). A união dos marcados vira o filtro
de Destinatário aplicado ao export. Nada selecionado = sem filtro.
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
        grupos: dict[str, list[str]],
        grupos_marcados: Iterable[str],
        pessoas_marcadas: Iterable[str],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Destinatários do export")
        self.resize(520, 640)

        nomes_users = sorted({n.strip() for n in nomes_disponiveis if n and n.strip()})
        self._grupos = dict(grupos)
        marcados_g = set(grupos_marcados)
        marcados_p = set(pessoas_marcadas)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        info = QLabel(
            "Marque grupos e/ou pessoas avulsas. Quem entrar em qualquer "
            "marcação aparece no export. Nada marcado = export inclui todos."
        )
        info.setObjectName("mutedLabel")
        info.setWordWrap(True)
        layout.addWidget(info)

        # ---- Seção: Grupos
        layout.addWidget(self._titulo("GRUPOS"))
        self._chk_grupos: dict[str, QCheckBox] = {}
        if not self._grupos:
            vazio = QLabel(
                "(nenhum grupo cadastrado — vá na aba 'Grupos' pra criar)"
            )
            vazio.setObjectName("mutedLabel")
            layout.addWidget(vazio)
        else:
            grupos_box = QVBoxLayout()
            grupos_box.setSpacing(2)
            for nome in sorted(self._grupos.keys()):
                n_membros = len(self._grupos[nome])
                chk = QCheckBox(f"{nome}  ({n_membros})")
                chk.setChecked(nome in marcados_g)
                chk.toggled.connect(self._atualizar_status)
                self._chk_grupos[nome] = chk
                grupos_box.addWidget(chk)
            layout.addLayout(grupos_box)

        # ---- Seção: Pessoas avulsas
        layout.addWidget(self._titulo("PESSOAS AVULSAS"))

        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Buscar pessoa…")
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
        cont_layout = QVBoxLayout(container)
        cont_layout.setContentsMargins(4, 4, 4, 4)
        cont_layout.setSpacing(2)
        self._chk_pessoas: dict[str, QCheckBox] = {}
        for nome in nomes_users:
            chk = QCheckBox(nome)
            chk.setChecked(nome in marcados_p)
            chk.toggled.connect(self._atualizar_status)
            self._chk_pessoas[nome] = chk
            cont_layout.addWidget(chk)
        cont_layout.addStretch(1)
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

    @staticmethod
    def _titulo(texto: str) -> QLabel:
        lab = QLabel(texto)
        lab.setObjectName("sectionLabel")
        return lab

    def _aplicar_busca(self, texto: str) -> None:
        q = texto.strip().lower()
        for nome, chk in self._chk_pessoas.items():
            chk.setVisible(q in nome.lower() if q else True)

    def _marcar_visiveis(self, valor: bool) -> None:
        for chk in self._chk_pessoas.values():
            if chk.isVisible():
                chk.setChecked(valor)

    def _atualizar_status(self) -> None:
        union: set[str] = {
            nome for nome, c in self._chk_pessoas.items() if c.isChecked()
        }
        for nome, chk in self._chk_grupos.items():
            if chk.isChecked():
                union.update(self._grupos.get(nome, []))
        n_g = sum(1 for c in self._chk_grupos.values() if c.isChecked())
        n_p = sum(1 for c in self._chk_pessoas.values() if c.isChecked())
        if not n_g and not n_p:
            self.lbl_status.setText("Sem filtro — export inclui todos os destinatários")
        else:
            self.lbl_status.setText(
                f"{n_g} grupo(s) + {n_p} pessoa(s) avulsa(s) "
                f"= {len(union)} usuário(s) no export"
            )

    def grupos_selecionados(self) -> list[str]:
        return [nome for nome, c in self._chk_grupos.items() if c.isChecked()]

    def pessoas_selecionadas(self) -> list[str]:
        return [nome for nome, c in self._chk_pessoas.items() if c.isChecked()]
