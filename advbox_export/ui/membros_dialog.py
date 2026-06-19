"""Dialog pra editar quem está num grupo específico.

Lista os 51 usuários da AdvBox com checkboxes; mantém só os marcados como
membros do grupo. Busca textual no topo, atalhos 'marcar/desmarcar todos'.
Botão de refresh manual recarrega a lista da API quando quiser.
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


class MembrosDialog(QDialog):
    def __init__(
        self,
        grupo: str,
        nomes_disponiveis: Iterable[str],
        marcados_iniciais: Iterable[str],
        on_refresh: Callable[[], Iterable[str] | None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Membros — {grupo}")
        self.resize(440, 600)

        self._on_refresh = on_refresh
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
            b.setProperty("variant", "ghost")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            atalhos.addWidget(b)
        atalhos.addStretch()
        if on_refresh is not None:
            self.btn_refresh = QPushButton("↻ Atualizar lista")
            self.btn_refresh.setProperty("variant", "ghost")
            self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_refresh.setToolTip(
                "Refaz a chamada /settings.users da AdvBox e atualiza a lista. "
                "Custa 1 requisição (~2s)."
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
        self._checkboxes: dict[str, QCheckBox] = {}
        self._montar_checkboxes(nomes_disponiveis, marcados)
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

    def _montar_checkboxes(
        self, nomes_disponiveis: Iterable[str], marcados: set[str]
    ) -> None:
        """(Re)constrói a lista de checkboxes. Limpa o que tiver antes."""
        while self._cl.count() > 0:
            item = self._cl.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._checkboxes.clear()

        nomes = sorted({n.strip() for n in nomes_disponiveis if n and n.strip()})
        for nome in nomes:
            chk = QCheckBox(nome)
            chk.setChecked(nome in marcados)
            chk.toggled.connect(self._atualizar_status)
            self._checkboxes[nome] = chk
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
        # Preserva marcações atuais (mesmo as visíveis filtradas pela busca).
        marcados_atuais = {n for n, c in self._checkboxes.items() if c.isChecked()}
        self._montar_checkboxes(novos, marcados_atuais)
        self._aplicar_busca(self.busca.text())
        self._atualizar_status()
        self.lbl_ultima_atualizacao.setText(
            f"Atualizado {datetime.now().strftime('%H:%M:%S')}"
        )

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
