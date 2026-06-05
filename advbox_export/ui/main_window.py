from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QDate, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QDesktopServices, QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDateEdit,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from advbox_export.core.client import AdvboxAuthError, AdvboxClient
from advbox_export.core.config import ConfigStore
from advbox_export.core.exporter import ExportProgress, ExportResult
from advbox_export.core.paths import (
    config_file,
    db_file,
    exports_dir,
    state_dir,
)
from advbox_export.core.worker import ExportWorker
from advbox_export.db import (
    STATUS_CANCELADO,
    STATUS_CONCLUIDO,
    STATUS_EM_ANDAMENTO,
    STATUS_FALHADO,
    ExportRepository,
    ExportRow,
)
from advbox_export.ui.settings_dialog import SettingsDialog
from advbox_export.ui.theme import apply_theme


STATUS_LABEL = {
    STATUS_EM_ANDAMENTO: "Em andamento",
    STATUS_CONCLUIDO: "Concluído",
    STATUS_FALHADO: "Falhou",
    STATUS_CANCELADO: "Cancelado",
}


class Card(QFrame):
    def __init__(self, titulo: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setFrameShape(QFrame.Shape.NoFrame)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 1)
        shadow.setColor(QColor(26, 36, 32, 18))  # ~7% do foreground
        self.setGraphicsEffect(shadow)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(20, 20, 20, 20)
        self._layout.setSpacing(12)

        titulo_label = QLabel(titulo)
        titulo_label.setObjectName("cardTitle")
        self._layout.addWidget(titulo_label)

    def add(self, w: QWidget) -> None:
        self._layout.addWidget(w)

    def add_layout(self, layout) -> None:
        self._layout.addLayout(layout)


class MainWindow(QMainWindow):
    pedir_token = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AdvBox Export")
        self.resize(1100, 760)

        self.config_store = ConfigStore(config_file())
        self.repository = ExportRepository(db_file())
        self._thread: QThread | None = None
        self._worker: ExportWorker | None = None

        self._build_menus()
        self._build_central()
        self._refresh_historico()

    # ---- Construção --------------------------------------------------------

    def _build_menus(self) -> None:
        menu = self.menuBar()
        m_arquivo = menu.addMenu("&Arquivo")
        m_arquivo.addAction(self._make_action("Sair", self.close, "Ctrl+Q"))

        m_config = menu.addMenu("&Configurações")
        m_config.addAction(self._make_action("Editar configurações…", self._abrir_settings))

        m_aparencia = menu.addMenu("&Aparência")
        self.act_tema_claro = QAction("Tema &claro", self)
        self.act_tema_claro.setCheckable(True)
        self.act_tema_claro.triggered.connect(lambda: self._mudar_tema("light"))
        self.act_tema_escuro = QAction("Tema &escuro", self)
        self.act_tema_escuro.setCheckable(True)
        self.act_tema_escuro.triggered.connect(lambda: self._mudar_tema("dark"))
        grupo_tema = QActionGroup(self)
        grupo_tema.setExclusive(True)
        grupo_tema.addAction(self.act_tema_claro)
        grupo_tema.addAction(self.act_tema_escuro)
        m_aparencia.addAction(self.act_tema_claro)
        m_aparencia.addAction(self.act_tema_escuro)
        tema_atual = self.config_store.load().theme
        self.act_tema_claro.setChecked(tema_atual == "light")
        self.act_tema_escuro.setChecked(tema_atual == "dark")

        m_ajuda = menu.addMenu("&Ajuda")
        m_ajuda.addAction(self._make_action("Sobre", self._sobre))

    def _make_action(self, texto: str, callback, shortcut: str | None = None) -> QAction:
        a = QAction(texto, self)
        a.triggered.connect(callback)
        if shortcut:
            a.setShortcut(shortcut)
        return a

    def _build_central(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        central = QWidget()
        central.setObjectName("centralWidget")
        scroll.setWidget(central)

        v = QVBoxLayout(central)
        v.setContentsMargins(32, 28, 32, 28)
        v.setSpacing(24)

        v.addLayout(self._build_header())
        v.addWidget(self._build_alerta_token())
        v.addWidget(self._build_card_novo_export())
        v.addWidget(self._build_card_andamento())
        v.addWidget(self._build_card_historico())
        v.addStretch()

        self.setCentralWidget(scroll)

    def _build_header(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(0, 0, 0, 4)

        sobretitulo = QLabel("FERRAMENTAS INTERNAS")
        sobretitulo.setObjectName("sectionLabel")
        layout.addWidget(sobretitulo)

        titulo = QLabel("AdvBox Export")
        f = QFont()
        f.setPointSize(22)
        f.setWeight(QFont.Weight.DemiBold)
        titulo.setFont(f)
        layout.addWidget(titulo)

        subtitulo = QLabel("Exporta atividades da AdvBox em XLSX e CSV sem o limite de 1.000 do painel web.")
        subtitulo.setObjectName("mutedLabel")
        subtitulo.setWordWrap(True)
        layout.addWidget(subtitulo)

        return layout

    def _build_card_novo_export(self) -> Card:
        card = Card("Novo export")

        atalhos_label = QLabel("ATALHOS DE PERÍODO")
        atalhos_label.setObjectName("sectionLabel")
        card.add(atalhos_label)

        atalhos = QHBoxLayout()
        atalhos.setSpacing(8)
        atalhos.setContentsMargins(0, 4, 0, 8)
        self.btn_group_atalhos = QButtonGroup(self)
        self.btn_group_atalhos.setExclusive(True)
        for label, range_fn in [
            ("Este mês", self._range_este_mes),
            ("Mês passado", self._range_mes_passado),
            ("Este ano", self._range_este_ano),
            ("Backfill completo", self._range_backfill),
        ]:
            btn = QPushButton(label)
            btn.setProperty("variant", "chip")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(range_fn)
            self.btn_group_atalhos.addButton(btn)
            atalhos.addWidget(btn)
        atalhos.addStretch()
        card.add_layout(atalhos)

        periodo_label = QLabel("PERÍODO")
        periodo_label.setObjectName("sectionLabel")
        card.add(periodo_label)

        hoje = QDate.currentDate()
        primeiro_dia_mes = QDate(hoje.year(), hoje.month(), 1)

        self.input_de = QDateEdit(primeiro_dia_mes)
        self.input_de.setCalendarPopup(True)
        self.input_de.setDisplayFormat("dd/MM/yyyy")
        self.input_de.dateChanged.connect(self._desmarcar_atalhos)

        self.input_ate = QDateEdit(hoje)
        self.input_ate.setCalendarPopup(True)
        self.input_ate.setDisplayFormat("dd/MM/yyyy")
        self.input_ate.dateChanged.connect(self._desmarcar_atalhos)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setContentsMargins(0, 4, 0, 4)
        form.addRow("De:", self.input_de)
        form.addRow("Até:", self.input_ate)
        card.add_layout(form)

        self.btn_exportar = QPushButton("Exportar agora")
        self.btn_exportar.setMinimumHeight(40)
        self.btn_exportar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_exportar.clicked.connect(self._iniciar_export)
        card.add(self.btn_exportar)

        return card

    def _build_alerta_token(self) -> QFrame:
        banner = QFrame()
        banner.setObjectName("alertCard")
        banner.setFrameShape(QFrame.Shape.NoFrame)

        sombra = QGraphicsDropShadowEffect(banner)
        sombra.setBlurRadius(10)
        sombra.setOffset(0, 1)
        sombra.setColor(QColor(0, 0, 0, 18))
        banner.setGraphicsEffect(sombra)

        layout = QHBoxLayout(banner)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(16)

        texto = QVBoxLayout()
        texto.setSpacing(2)
        titulo = QLabel("Token AdvBox não configurado")
        titulo.setObjectName("alertTitle")
        corpo = QLabel(
            "Configure o token antes de exportar — ele fica gravado só no seu computador."
        )
        corpo.setObjectName("alertBody")
        corpo.setWordWrap(True)
        texto.addWidget(titulo)
        texto.addWidget(corpo)
        layout.addLayout(texto, 1)

        btn_config = QPushButton("Configurar agora")
        btn_config.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_config.clicked.connect(self._abrir_settings)
        layout.addWidget(btn_config, 0, Qt.AlignmentFlag.AlignVCenter)

        self.alerta_token = banner
        self._refresh_alerta_token()
        return banner

    def _refresh_alerta_token(self) -> None:
        if hasattr(self, "alerta_token"):
            self.alerta_token.setVisible(not self.config_store.is_configured())

    def _build_card_andamento(self) -> Card:
        card = Card("Em andamento")

        self.lbl_progresso = QLabel("—")
        self.lbl_progresso.setObjectName("mutedLabel")
        card.add(self.lbl_progresso)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        card.add(self.progress_bar)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        self.log_view.setMinimumHeight(200)
        card.add(self.log_view)

        cancelar_row = QHBoxLayout()
        cancelar_row.addStretch()
        self.btn_cancelar = QPushButton("Cancelar export")
        self.btn_cancelar.setProperty("variant", "danger")
        self.btn_cancelar.clicked.connect(self._cancelar_export)
        cancelar_row.addWidget(self.btn_cancelar)
        card.add_layout(cancelar_row)

        self.card_andamento = card
        card.setVisible(False)
        return card

    def _build_card_historico(self) -> Card:
        card = Card("Histórico")

        topo = QHBoxLayout()
        topo.addStretch()
        btn_pasta = QPushButton("Abrir pasta de exports")
        btn_pasta.setProperty("variant", "outline")
        btn_pasta.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_pasta.clicked.connect(self._abrir_pasta_exports)
        topo.addWidget(btn_pasta)
        btn_refresh = QPushButton("Atualizar")
        btn_refresh.setProperty("variant", "ghost")
        btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_refresh.clicked.connect(self._refresh_historico)
        topo.addWidget(btn_refresh)
        card.add_layout(topo)

        self.tabela = QTableWidget(0, 7)
        self.tabela.setHorizontalHeaderLabels(
            ["Data", "Período", "Total", "Status", "Duração", "Erro", "Ações"]
        )
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.verticalHeader().setDefaultSectionSize(42)
        self.tabela.verticalHeader().setMinimumSectionSize(42)
        self.tabela.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabela.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabela.setAlternatingRowColors(True)
        self.tabela.setShowGrid(False)
        header = self.tabela.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.tabela.setColumnWidth(0, 150)
        self.tabela.setColumnWidth(1, 230)
        self.tabela.setColumnWidth(2, 90)
        self.tabela.setColumnWidth(3, 110)
        self.tabela.setColumnWidth(4, 90)
        self.tabela.setColumnWidth(6, 230)
        self.tabela.setMinimumHeight(320)
        card.add(self.tabela)

        return card

    # ---- Atalhos de range --------------------------------------------------

    def _setar_datas_silenciosamente(self, de: QDate, ate: QDate) -> None:
        """Muda as datas sem disparar dateChanged (que deselecionaria o atalho)."""
        self.input_de.blockSignals(True)
        self.input_ate.blockSignals(True)
        try:
            self.input_de.setDate(de)
            self.input_ate.setDate(ate)
        finally:
            self.input_de.blockSignals(False)
            self.input_ate.blockSignals(False)

    def _desmarcar_atalhos(self) -> None:
        checado = self.btn_group_atalhos.checkedButton()
        if checado is None:
            return
        self.btn_group_atalhos.setExclusive(False)
        checado.setChecked(False)
        self.btn_group_atalhos.setExclusive(True)

    def _range_este_mes(self) -> None:
        hoje = QDate.currentDate()
        self._setar_datas_silenciosamente(QDate(hoje.year(), hoje.month(), 1), hoje)

    def _range_mes_passado(self) -> None:
        hoje = QDate.currentDate()
        primeiro = QDate(hoje.year(), hoje.month(), 1).addMonths(-1)
        ultimo = primeiro.addMonths(1).addDays(-1)
        self._setar_datas_silenciosamente(primeiro, ultimo)

    def _range_este_ano(self) -> None:
        hoje = QDate.currentDate()
        self._setar_datas_silenciosamente(QDate(hoje.year(), 1, 1), hoje)

    def _range_backfill(self) -> None:
        hoje = QDate.currentDate()
        self._setar_datas_silenciosamente(QDate(hoje.year() - 6, 1, 1), hoje)

    def _mudar_tema(self, theme: str) -> None:
        cfg = self.config_store.load()
        cfg.theme = theme
        self.config_store.save(cfg)
        apply_theme(QApplication.instance(), theme=theme)

    # ---- Ações principais --------------------------------------------------

    def _iniciar_export(self) -> None:
        if self._thread is not None:
            QMessageBox.information(self, "Já em andamento", "Já existe um export em andamento.")
            return

        cfg = self.config_store.load()
        if not cfg.token:
            QMessageBox.warning(
                self,
                "Token não configurado",
                "Configure o token AdvBox em Configurações antes de exportar.",
            )
            self._abrir_settings()
            return

        try:
            client = AdvboxClient(token=cfg.token, base_url=cfg.base_url)
        except AdvboxAuthError as e:
            QMessageBox.critical(self, "Erro", str(e))
            return

        date_from = self.input_de.date().toPython()
        date_to = self.input_ate.date().toPython()
        if date_to < date_from:
            QMessageBox.warning(self, "Período inválido", "A data final é anterior à inicial.")
            return

        self._preparar_ui_andamento(date_from, date_to)

        self._worker = ExportWorker(
            client=client,
            repository=self.repository,
            exports_dir=exports_dir(),
            state_dir=state_dir(),
            date_from=date_from,
            date_to=date_to,
        )
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)

        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(self._on_log)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        self._thread.started.connect(self._worker.start)

        # cleanup
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._worker.cancelled.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_worker)

        self._thread.start()

    def _cancelar_export(self) -> None:
        if self._worker is not None:
            self._worker.request_stop()
            self.btn_cancelar.setEnabled(False)
            self.btn_cancelar.setText("Cancelando…")

    def _preparar_ui_andamento(self, date_from: date, date_to: date) -> None:
        self.log_view.clear()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.lbl_progresso.setText(
            f"Período {date_from.isoformat()} → {date_to.isoformat()}: iniciando…"
        )
        self.card_andamento.setVisible(True)
        self.btn_exportar.setEnabled(False)
        self.btn_cancelar.setEnabled(True)
        self.btn_cancelar.setText("Cancelar")

    # ---- Slots dos signals do worker --------------------------------------

    def _on_progress(self, p: ExportProgress) -> None:
        if p.total_estimado > 0:
            pct = min(100, int(p.total_baixado * 100 / p.total_estimado))
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(pct)
        else:
            self.progress_bar.setRange(0, 0)  # indeterminado
        self.lbl_progresso.setText(
            f"Janela {p.janela_indice}/{p.janelas_total} ({p.janela_label}) — "
            f"{p.total_baixado} baixadas (estimativa {p.total_estimado})"
        )

    def _on_log(self, nivel: str, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"{ts} [{nivel}] {msg}")

    def _on_finished(self, resultado: ExportResult) -> None:
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.lbl_progresso.setText(
            f"Concluído: {resultado.total_atividades} atividades em {resultado.duracao_segundos:.0f}s"
        )
        self.btn_exportar.setEnabled(True)
        self.btn_cancelar.setEnabled(False)
        self._refresh_historico()
        QMessageBox.information(
            self,
            "Export concluído",
            f"{resultado.total_atividades} atividades exportadas.\n\n"
            f"XLSX: {resultado.xlsx_path}\nCSV: {resultado.csv_path}",
        )

    def _on_failed(self, mensagem: str) -> None:
        self.btn_exportar.setEnabled(True)
        self.btn_cancelar.setEnabled(False)
        self.lbl_progresso.setText(f"Falhou: {mensagem}")
        self._refresh_historico()
        QMessageBox.critical(self, "Export falhou", mensagem)

    def _on_cancelled(self) -> None:
        self.btn_exportar.setEnabled(True)
        self.btn_cancelar.setEnabled(False)
        self.lbl_progresso.setText("Cancelado — você pode retomar rodando de novo o mesmo período.")
        self._refresh_historico()

    def _cleanup_worker(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None

    # ---- Histórico ---------------------------------------------------------

    def _refresh_historico(self) -> None:
        rows = self.repository.listar(limite=200)
        self.tabela.setRowCount(len(rows))
        for i, row in enumerate(rows):
            self._fill_row(i, row)

    def _fill_row(self, i: int, row: ExportRow) -> None:
        data_fmt = self._format_datetime(row.criado_em)
        periodo = f"{row.periodo_inicio} → {row.periodo_fim}"
        total = "" if row.total_registros is None else f"{row.total_registros:,}".replace(",", ".")
        status = STATUS_LABEL.get(row.status, row.status)
        duracao = (
            f"{row.duracao_segundos:.0f}s" if row.duracao_segundos is not None else ""
        )
        erro = row.erro_mensagem or ""

        self.tabela.setItem(i, 0, QTableWidgetItem(data_fmt))
        self.tabela.setItem(i, 1, QTableWidgetItem(periodo))
        item_total = QTableWidgetItem(total)
        item_total.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.tabela.setItem(i, 2, item_total)
        self.tabela.setItem(i, 3, QTableWidgetItem(status))
        self.tabela.setItem(i, 4, QTableWidgetItem(duracao))
        self.tabela.setItem(i, 5, QTableWidgetItem(erro))
        self.tabela.setCellWidget(i, 6, self._build_acoes_widget(row))

    @staticmethod
    def _format_datetime(iso: str) -> str:
        try:
            dt = datetime.fromisoformat(iso)
            return dt.strftime("%d/%m/%Y %H:%M")
        except (ValueError, TypeError):
            return iso

    def _build_acoes_widget(self, row: ExportRow) -> QWidget:
        w = QFrame()
        w.setFrameShape(QFrame.Shape.NoFrame)
        w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        w.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        w.setFixedHeight(40)
        h = QHBoxLayout(w)
        h.setContentsMargins(8, 6, 8, 6)
        h.setSpacing(6)
        h.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        for label, path in [
            ("XLSX", row.caminho_xlsx),
            ("CSV", row.caminho_csv),
            ("Log", row.caminho_log),
        ]:
            btn = QPushButton(label)
            btn.setProperty("variant", "outline-sm")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            btn.setFixedHeight(26)
            existe = bool(path) and Path(path).exists() if path else False
            btn.setEnabled(existe)
            if path:
                btn.clicked.connect(lambda _checked=False, p=path: self._abrir_arquivo(p))
            h.addWidget(btn)

        h.addStretch()
        return w

    def _abrir_arquivo(self, caminho: str) -> None:
        p = Path(caminho)
        if not p.exists():
            QMessageBox.warning(self, "Arquivo não encontrado", str(p))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))

    def _abrir_pasta_exports(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(exports_dir())))

    # ---- Menu actions ------------------------------------------------------

    def _abrir_settings(self) -> None:
        dlg = SettingsDialog(self.config_store, parent=self)
        dlg.exec()
        self._refresh_alerta_token()

    def _sobre(self) -> None:
        from advbox_export import __version__

        QMessageBox.about(
            self,
            "Sobre AdvBox Export",
            f"<b>AdvBox Export</b> {__version__}<br>"
            "Exportador de atividades AdvBox para XLSX/CSV.<br><br>"
            f"Config: {config_file()}<br>"
            f"Dados: {db_file().parent}",
        )

    # ---- Cleanup ao fechar -------------------------------------------------

    def closeEvent(self, event) -> None:
        if self._worker is not None:
            reply = QMessageBox.question(
                self,
                "Export em andamento",
                "Há um export em andamento. Cancelar e sair?\n"
                "(O progresso atual fica salvo e você pode retomar depois.)",
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._worker.request_stop()
            if self._thread is not None:
                self._thread.quit()
                self._thread.wait(3000)
        event.accept()
