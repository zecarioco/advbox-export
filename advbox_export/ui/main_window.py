from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QDate, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont, QIcon
from PySide6.QtWidgets import (
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

        # Se não há token na primeira execução, sugere abrir Settings
        if not self.config_store.is_configured():
            self.statusBar().showMessage(
                "Token não configurado — clique em Configurações pra colar o token AdvBox."
            )

    # ---- Construção --------------------------------------------------------

    def _build_menus(self) -> None:
        menu = self.menuBar()
        m_arquivo = menu.addMenu("&Arquivo")
        m_arquivo.addAction(self._make_action("Abrir pasta de exports", self._abrir_pasta_exports))
        m_arquivo.addSeparator()
        m_arquivo.addAction(self._make_action("Sair", self.close, "Ctrl+Q"))

        m_config = menu.addMenu("&Configurações")
        m_config.addAction(self._make_action("Editar configurações…", self._abrir_settings))

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

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        hoje = QDate.currentDate()
        primeiro_dia_mes = QDate(hoje.year(), hoje.month(), 1)

        self.input_de = QDateEdit(primeiro_dia_mes)
        self.input_de.setCalendarPopup(True)
        self.input_de.setDisplayFormat("dd/MM/yyyy")
        self.input_ate = QDateEdit(hoje)
        self.input_ate.setCalendarPopup(True)
        self.input_ate.setDisplayFormat("dd/MM/yyyy")

        form.addRow("De:", self.input_de)
        form.addRow("Até:", self.input_ate)
        card.add_layout(form)

        atalhos_label = QLabel("ATALHOS")
        atalhos_label.setObjectName("sectionLabel")
        card.add(atalhos_label)

        atalhos = QHBoxLayout()
        atalhos.setSpacing(8)
        for label, range_fn in [
            ("Este mês", self._range_este_mes),
            ("Mês passado", self._range_mes_passado),
            ("Este ano", self._range_este_ano),
            ("Backfill completo", self._range_backfill),
        ]:
            btn = QPushButton(label)
            btn.setProperty("variant", "ghost")
            btn.clicked.connect(range_fn)
            atalhos.addWidget(btn)
        atalhos.addStretch()
        card.add_layout(atalhos)

        self.btn_exportar = QPushButton("Exportar agora")
        self.btn_exportar.setMinimumHeight(40)
        self.btn_exportar.clicked.connect(self._iniciar_export)
        botoes_row = QHBoxLayout()
        botoes_row.addStretch()
        botoes_row.addWidget(self.btn_exportar)
        card.add_layout(botoes_row)

        return card

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
        btn_refresh = QPushButton("Atualizar")
        btn_refresh.setProperty("variant", "ghost")
        btn_refresh.clicked.connect(self._refresh_historico)
        topo.addWidget(btn_refresh)
        card.add_layout(topo)

        self.tabela = QTableWidget(0, 7)
        self.tabela.setHorizontalHeaderLabels(
            ["Data", "Período", "Total", "Status", "Duração", "Erro", "Ações"]
        )
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabela.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabela.setAlternatingRowColors(True)
        header = self.tabela.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.tabela.setColumnWidth(0, 140)
        self.tabela.setColumnWidth(1, 140)
        self.tabela.setColumnWidth(2, 90)
        self.tabela.setColumnWidth(3, 110)
        self.tabela.setColumnWidth(4, 90)
        self.tabela.setColumnWidth(6, 220)
        self.tabela.setMinimumHeight(280)
        card.add(self.tabela)

        return card

    # ---- Atalhos de range --------------------------------------------------

    def _range_este_mes(self) -> None:
        hoje = QDate.currentDate()
        self.input_de.setDate(QDate(hoje.year(), hoje.month(), 1))
        self.input_ate.setDate(hoje)

    def _range_mes_passado(self) -> None:
        hoje = QDate.currentDate()
        primeiro = QDate(hoje.year(), hoje.month(), 1).addMonths(-1)
        ultimo = primeiro.addMonths(1).addDays(-1)
        self.input_de.setDate(primeiro)
        self.input_ate.setDate(ultimo)

    def _range_este_ano(self) -> None:
        hoje = QDate.currentDate()
        self.input_de.setDate(QDate(hoje.year(), 1, 1))
        self.input_ate.setDate(hoje)

    def _range_backfill(self) -> None:
        hoje = QDate.currentDate()
        self.input_de.setDate(QDate(hoje.year() - 6, 1, 1))
        self.input_ate.setDate(hoje)

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
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        h = QHBoxLayout(w)
        h.setContentsMargins(4, 2, 4, 2)
        h.setSpacing(6)

        for label, path in [
            ("XLSX", row.caminho_xlsx),
            ("CSV", row.caminho_csv),
            ("Log", row.caminho_log),
        ]:
            btn = QPushButton(label)
            btn.setProperty("variant", "outline")
            btn.setMinimumHeight(28)
            btn.setMaximumHeight(28)
            btn.setStyleSheet("padding: 2px 10px; font-size: 12px;")
            btn.setEnabled(bool(path) and Path(path).exists() if path else False)
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
