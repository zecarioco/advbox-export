"""Aba de gerenciamento de grupos.

A API da AdvBox não expõe grupos publicamente, então é manual. Cada grupo
aparece como um card com nome + contagem de membros + menu de ações
(Editar nome / Editar pessoas / Excluir).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from advbox_export.core.client import AdvboxClient
from advbox_export.core.config import ConfigStore
from advbox_export.ui.membros_dialog import MembrosDialog


class GruposTab(QWidget):
    """Lista de grupos como cards com menu '⋯'."""

    grupos_alterados = Signal()

    def __init__(self, config_store: ConfigStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config_store = config_store
        self._nomes_cache: list[str] | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        info = QLabel(
            "Crie grupos pra simular as equipes do escritório — a API da "
            "AdvBox não expõe grupos. Cada export pode incluir um ou mais "
            "grupos, além de pessoas avulsas."
        )
        info.setObjectName("mutedLabel")
        info.setWordWrap(True)
        layout.addWidget(info)

        topo = QHBoxLayout()
        topo.addStretch()
        btn_novo = QPushButton("+ Novo grupo")
        btn_novo.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_novo.clicked.connect(self._novo_grupo)
        topo.addWidget(btn_novo)
        layout.addLayout(topo)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._lista_container = QWidget()
        self._lista_layout = QVBoxLayout(self._lista_container)
        self._lista_layout.setContentsMargins(0, 0, 0, 0)
        self._lista_layout.setSpacing(10)
        self._lista_layout.addStretch(1)
        scroll.setWidget(self._lista_container)
        layout.addWidget(scroll, 1)

        self._refresh()

    # ---- Render -----------------------------------------------------------

    def _refresh(self) -> None:
        while self._lista_layout.count() > 0:
            item = self._lista_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        cfg = self.config_store.load()
        nomes_grupos = sorted(cfg.grupos.keys())

        if not nomes_grupos:
            vazio = QLabel(
                "Nenhum grupo cadastrado ainda. Clique em '+ Novo grupo' pra criar."
            )
            vazio.setObjectName("mutedLabel")
            vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vazio.setContentsMargins(0, 32, 0, 32)
            self._lista_layout.addWidget(vazio)
        else:
            for nome in nomes_grupos:
                self._lista_layout.addWidget(
                    self._build_card_grupo(nome, cfg.grupos[nome])
                )
        self._lista_layout.addStretch(1)

    def _build_card_grupo(self, nome: str, membros: list[str]) -> QFrame:
        card = QFrame()
        card.setObjectName("grupoCard")
        card.setFrameShape(QFrame.Shape.NoFrame)
        h = QHBoxLayout(card)
        h.setContentsMargins(20, 14, 14, 14)
        h.setSpacing(12)

        texto = QVBoxLayout()
        texto.setSpacing(2)
        lbl_nome = QLabel(f"GRUPO: {nome}")
        lbl_nome.setObjectName("grupoNome")
        lbl_sub = QLabel(
            f"{len(membros)} pessoa(s)" if membros else "sem membros ainda"
        )
        lbl_sub.setObjectName("grupoSubtitulo")
        texto.addWidget(lbl_nome)
        texto.addWidget(lbl_sub)
        h.addLayout(texto, 1)

        botao_menu = QToolButton()
        botao_menu.setObjectName("grupoMenu")
        botao_menu.setText("⋯")
        botao_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        botao_menu.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        botao_menu.setToolTip("Ações do grupo")

        menu = QMenu(botao_menu)
        act_pessoas = QAction("Editar pessoas…", menu)
        act_pessoas.triggered.connect(lambda _checked=False, n=nome: self._editar_pessoas(n))
        act_renomear = QAction("Renomear grupo…", menu)
        act_renomear.triggered.connect(lambda _checked=False, n=nome: self._renomear(n))
        menu.addAction(act_pessoas)
        menu.addAction(act_renomear)
        menu.addSeparator()
        act_excluir = QAction("Excluir grupo", menu)
        act_excluir.triggered.connect(lambda _checked=False, n=nome: self._excluir(n))
        menu.addAction(act_excluir)

        botao_menu.setMenu(menu)
        h.addWidget(botao_menu, 0, Qt.AlignmentFlag.AlignVCenter)
        return card

    # ---- API de usuários (lazy + cache) -----------------------------------

    def _carregar_nomes(self) -> list[str] | None:
        if self._nomes_cache is not None:
            return self._nomes_cache
        cfg = self.config_store.load()
        if not cfg.token:
            return None
        try:
            client = AdvboxClient(token=cfg.token, base_url=cfg.base_url)
            users = client.list_users()
        except Exception:
            return None
        nomes = sorted({u.get("name", "").strip() for u in users if u.get("name")})
        self._nomes_cache = nomes
        return nomes

    # ---- Ações ------------------------------------------------------------

    def _novo_grupo(self) -> None:
        nome, ok = QInputDialog.getText(self, "Novo grupo", "Nome do grupo:")
        nome = (nome or "").strip()
        if not ok or not nome:
            return
        cfg = self.config_store.load()
        if nome in cfg.grupos:
            QMessageBox.warning(self, "Já existe", f"Já existe um grupo chamado '{nome}'.")
            return
        cfg.grupos[nome] = []
        self.config_store.save(cfg)
        self._refresh()
        self.grupos_alterados.emit()
        # Abre o editor de pessoas direto, pra fluir o cadastro
        self._editar_pessoas(nome)

    def _renomear(self, antigo: str) -> None:
        novo, ok = QInputDialog.getText(
            self, "Renomear grupo", "Novo nome:", text=antigo
        )
        novo = (novo or "").strip()
        if not ok or not novo or novo == antigo:
            return
        cfg = self.config_store.load()
        if novo in cfg.grupos:
            QMessageBox.warning(self, "Já existe", f"Já existe um grupo chamado '{novo}'.")
            return
        cfg.grupos[novo] = cfg.grupos.pop(antigo)
        cfg.grupos_selecionados = [
            novo if g == antigo else g for g in cfg.grupos_selecionados
        ]
        self.config_store.save(cfg)
        self._refresh()
        self.grupos_alterados.emit()

    def _excluir(self, nome: str) -> None:
        resp = QMessageBox.question(
            self,
            "Excluir grupo",
            f"Excluir o grupo '{nome}'?\n\n"
            "Os membros continuam cadastrados na AdvBox — só a definição "
            "do grupo aqui no app vai embora.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return
        cfg = self.config_store.load()
        cfg.grupos.pop(nome, None)
        cfg.grupos_selecionados = [g for g in cfg.grupos_selecionados if g != nome]
        self.config_store.save(cfg)
        self._refresh()
        self.grupos_alterados.emit()

    def _editar_pessoas(self, nome: str) -> None:
        nomes = self._carregar_nomes()
        if nomes is None:
            QMessageBox.warning(
                self,
                "Sem lista de usuários",
                "Não foi possível carregar a lista de usuários da AdvBox. "
                "Verifique o token em Configurações.",
            )
            return
        cfg = self.config_store.load()
        atuais = set(cfg.grupos.get(nome, []))
        dlg = MembrosDialog(grupo=nome, nomes_disponiveis=nomes, marcados_iniciais=atuais, parent=self)
        from PySide6.QtWidgets import QDialog
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        cfg.grupos[nome] = sorted(dlg.selecionados())
        self.config_store.save(cfg)
        self._refresh()
        self.grupos_alterados.emit()
