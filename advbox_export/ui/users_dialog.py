"""Dialog de seleção de destinatários do próximo export.

Mostra duas seções: grupos cadastrados (com contagem de membros) e pessoas
avulsas (todos os 51 users da AdvBox). A união dos marcados vira o filtro
de Destinatário aplicado ao export. Nada selecionado = sem filtro.

Botão de refresh manual recarrega a lista de pessoas da API quando quiser
(grupos vêm do config local, não precisam de refresh).
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable, Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
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
        on_refresh: Callable[[], Iterable[str] | None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Destinatários do export")
        self.resize(520, 640)

        self._on_refresh = on_refresh
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
            b.setProperty("variant", "ghost")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            atalhos.addWidget(b)
        atalhos.addStretch()
        if on_refresh is not None:
            self.btn_refresh = QPushButton("↻ Atualizar lista")
            self.btn_refresh.setProperty("variant", "ghost")
            self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_refresh.setToolTip(
                "Refaz a chamada /settings.users da AdvBox e atualiza as "
                "pessoas avulsas. Custa 1 requisição (~2s)."
            )
            self.btn_refresh.clicked.connect(self._atualizar_lista)
            atalhos.addWidget(self.btn_refresh)
        layout.addLayout(atalhos)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        self._cl = QVBoxLayout(container)
        self._cl.setContentsMargins(4, 4, 4, 4)
        self._cl.setSpacing(2)
        self._chk_pessoas: dict[str, QCheckBox] = {}
        self._montar_pessoas(nomes_disponiveis, marcados_p)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        rodape = QHBoxLayout()
        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("mutedLabel")
        rodape.addWidget(self.lbl_status)
        rodape.addStretch()
        self.lbl_ultima_atualizacao = QLabel("")
        self.lbl_ultima_atualizacao.setObjectName("mutedLabel")
        rodape.addWidget(self.lbl_ultima_atualizacao)
        layout.addLayout(rodape)
        self._atualizar_status()

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def _montar_pessoas(
        self, nomes_disponiveis: Iterable[str], marcados: set[str]
    ) -> None:
        """(Re)constrói os checkboxes de pessoas. Limpa o que tiver antes."""
        while self._cl.count() > 0:
            item = self._cl.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._chk_pessoas.clear()

        nomes = sorted({n.strip() for n in nomes_disponiveis if n and n.strip()})
        for nome in nomes:
            chk = QCheckBox(nome)
            chk.setChecked(nome in marcados)
            chk.toggled.connect(self._atualizar_status)
            self._chk_pessoas[nome] = chk
            self._cl.addWidget(chk)
        self._cl.addStretch(1)

    def _atualizar_lista(self) -> None:
        if self._on_refresh is None:
            return
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("↻ Atualizando…")
        # Força o Qt a repintar antes da request bloquear a thread (~2s).
        QApplication.processEvents()
        try:
            novos = self._on_refresh()
        finally:
            self.btn_refresh.setEnabled(True)
            self.btn_refresh.setText("↻ Atualizar lista")
        if novos is None:
            QMessageBox.warning(
                self,
                "Falha ao atualizar",
                "Não foi possível buscar a lista atualizada. Verifique o token "
                "ou a conexão e tente de novo.",
            )
            return
        marcados_atuais = {n for n, c in self._chk_pessoas.items() if c.isChecked()}
        self._montar_pessoas(novos, marcados_atuais)
        self._aplicar_busca(self.busca.text())
        self._atualizar_status()
        self.lbl_ultima_atualizacao.setText(
            f"Atualizado {datetime.now().strftime('%H:%M:%S')}"
        )

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
