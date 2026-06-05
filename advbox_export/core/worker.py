from __future__ import annotations

import io
import logging
import time
from datetime import date
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from advbox_export.core.client import AdvboxClient
from advbox_export.core.exporter import (
    ExportCancelado,
    ExportProgress,
    Exporter,
)
from advbox_export.core.storage import slug_periodo
from advbox_export.db import ExportRepository


class ExportWorker(QObject):
    """Roda o Exporter em background, expondo signals pra UI.

    Padrão: criar worker -> moveToThread(thread) -> thread.started.connect(worker.start)
    """

    progress = Signal(object)  # ExportProgress
    log = Signal(str, str)  # (nivel, msg)
    finished = Signal(object)  # ExportResult
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        *,
        client: AdvboxClient,
        repository: ExportRepository,
        exports_dir: Path,
        state_dir: Path,
        date_from: date,
        date_to: date,
    ) -> None:
        super().__init__()
        self._client = client
        self._repository = repository
        self._exports_dir = exports_dir
        self._state_dir = state_dir
        self._date_from = date_from
        self._date_to = date_to
        self._stop_requested = False
        self._log_buffer = io.StringIO()
        self._export_id: int | None = None
        self._inicio: float = 0.0

    @Slot()
    def request_stop(self) -> None:
        self._stop_requested = True

    @Slot()
    def start(self) -> None:
        self._inicio = time.monotonic()
        self._export_id = self._repository.criar(
            periodo_inicio=self._date_from.isoformat(),
            periodo_fim=self._date_to.isoformat(),
        )

        exporter = Exporter(
            client=self._client,
            exports_dir=self._exports_dir,
            state_dir=self._state_dir,
        )

        try:
            resultado = exporter.run(
                date_from=self._date_from,
                date_to=self._date_to,
                progress_cb=self._on_progress,
                log_cb=self._on_log,
                should_stop=lambda: self._stop_requested,
            )
        except ExportCancelado:
            log_path = self._dump_log()
            self._repository.marcar_cancelado(
                self._export_id,
                caminho_log=str(log_path) if log_path else None,
                duracao_segundos=time.monotonic() - self._inicio,
            )
            self.cancelled.emit()
            return
        except Exception as exc:
            logging.getLogger(__name__).exception("export falhou")
            self._on_log("ERROR", f"export falhou: {exc}")
            log_path = self._dump_log()
            self._repository.marcar_falhado(
                self._export_id,
                erro_mensagem=str(exc),
                caminho_log=str(log_path) if log_path else None,
                duracao_segundos=time.monotonic() - self._inicio,
            )
            self.failed.emit(str(exc))
            return

        log_path = self._dump_log()
        self._repository.marcar_concluido(
            self._export_id,
            caminho_xlsx=str(resultado.xlsx_path),
            caminho_csv=str(resultado.csv_path),
            caminho_log=str(log_path) if log_path else None,
            total_registros=resultado.total_atividades,
            duracao_segundos=resultado.duracao_segundos,
        )
        self.finished.emit(resultado)

    def _on_progress(self, p: ExportProgress) -> None:
        self.progress.emit(p)

    def _on_log(self, nivel: str, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        linha = f"{ts} [{nivel}] {msg}"
        self._log_buffer.write(linha + "\n")
        self.log.emit(nivel, msg)

    def _dump_log(self) -> Path | None:
        if not self._log_buffer.getvalue():
            return None
        slug = slug_periodo(self._date_from, self._date_to)
        log_path = self._exports_dir / f"{slug}_atividades.log"
        # se já existe (run anterior), renomeia pra _v2, _v3
        if log_path.exists():
            n = 2
            while True:
                cand = self._exports_dir / f"{slug}_atividades_v{n}.log"
                if not cand.exists():
                    log_path = cand
                    break
                n += 1
        log_path.write_text(self._log_buffer.getvalue(), encoding="utf-8")
        return log_path
