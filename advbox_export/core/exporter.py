from __future__ import annotations

import calendar
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from advbox_export.core.client import AdvboxClient
from advbox_export.core.storage import (
    PeriodoArquivo,
    gerar_csv,
    gerar_xlsx,
    gravar_jsonl_append,
    proximo_caminho_versionado,
    slug_periodo,
)

logger = logging.getLogger(__name__)

PAGE_SIZE = 1000
STATE_VERSION = 1

CHAVES_ATIVIDADE_CONHECIDAS = {
    "id",
    "date",
    "date_deadline",
    "task",
    "reward",
    "notes",
    "local",
    "lawsuits_id",
    "created_at",
    "lawsuit",
    "users",
}


@dataclass
class Janela:
    inicio: str  # YYYY-MM-DD
    fim: str

    def label(self) -> str:
        if self.inicio[:7] == self.fim[:7]:
            return self.inicio[:7]
        return f"{self.inicio} → {self.fim}"


@dataclass
class ExportState:
    version: int
    periodo_inicio: str
    periodo_fim: str
    jsonl_path: str
    janelas_concluidas: list[str] = field(default_factory=list)  # labels
    janela_atual: Janela | None = None
    offset_atual: int = 0
    total_baixado: int = 0
    iniciado_em: str = ""

    @classmethod
    def from_dict(cls, raw: dict) -> "ExportState":
        janela_atual_raw = raw.get("janela_atual")
        janela_atual = Janela(**janela_atual_raw) if janela_atual_raw else None
        return cls(
            version=raw["version"],
            periodo_inicio=raw["periodo_inicio"],
            periodo_fim=raw["periodo_fim"],
            jsonl_path=raw["jsonl_path"],
            janelas_concluidas=list(raw.get("janelas_concluidas", [])),
            janela_atual=janela_atual,
            offset_atual=int(raw.get("offset_atual", 0)),
            total_baixado=int(raw.get("total_baixado", 0)),
            iniciado_em=raw.get("iniciado_em", ""),
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.janela_atual is None:
            d["janela_atual"] = None
        return d


@dataclass
class ExportProgress:
    janela_label: str
    janela_indice: int
    janelas_total: int
    offset_atual: int
    total_baixado: int
    total_estimado: int  # soma de totalCount conhecido até agora
    msg: str = ""


@dataclass
class ExportResult:
    xlsx_path: Path
    csv_path: Path
    total_atividades: int
    duracao_segundos: float
    periodo_inicio: date
    periodo_fim: date


class ExportCancelado(Exception):
    pass


LogCallback = Callable[[str, str], None]  # (nivel, msg)
ProgressCallback = Callable[[ExportProgress], None]
StopChecker = Callable[[], bool]


def _janelas_mensais(inicio: date, fim: date) -> list[Janela]:
    """Divide [inicio, fim] em janelas mensais fechadas pelos limites."""
    if fim < inicio:
        raise ValueError(f"fim {fim} é anterior a inicio {inicio}")

    janelas: list[Janela] = []
    cursor = inicio
    while cursor <= fim:
        ultimo_dia_mes = calendar.monthrange(cursor.year, cursor.month)[1]
        fim_mes = date(cursor.year, cursor.month, ultimo_dia_mes)
        fim_janela = min(fim_mes, fim)
        janelas.append(
            Janela(inicio=cursor.isoformat(), fim=fim_janela.isoformat())
        )
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return janelas


class Exporter:
    def __init__(
        self,
        client: AdvboxClient,
        exports_dir: Path,
        state_dir: Path,
    ) -> None:
        self.client = client
        self.exports_dir = exports_dir
        self.state_dir = state_dir
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._chaves_logadas = False

    def _state_path(self, slug: str) -> Path:
        return self.state_dir / f"{slug}.json"

    def _carregar_state(self, path: Path) -> ExportState | None:
        if not path.exists():
            return None
        try:
            return ExportState.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("state file %s inválido (%s) — ignorando", path, exc)
            return None

    def _salvar_state(self, path: Path, state: ExportState) -> None:
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def run(
        self,
        date_from: date,
        date_to: date,
        *,
        progress_cb: ProgressCallback | None = None,
        log_cb: LogCallback | None = None,
        should_stop: StopChecker | None = None,
    ) -> ExportResult:
        log = log_cb or (lambda lvl, msg: logger.log(getattr(logging, lvl, logging.INFO), msg))
        emit = progress_cb or (lambda p: None)
        stop = should_stop or (lambda: False)

        periodo = PeriodoArquivo(
            slug=slug_periodo(date_from, date_to),
            inicio=date_from,
            fim=date_to,
        )
        state_path = self._state_path(periodo.slug)
        state = self._carregar_state(state_path)

        if state and (
            state.periodo_inicio != date_from.isoformat()
            or state.periodo_fim != date_to.isoformat()
        ):
            log("WARN", f"state file {state_path.name} é de outro período — começando do zero")
            state_path.unlink(missing_ok=True)
            state = None

        janelas = _janelas_mensais(date_from, date_to)

        if state is None:
            jsonl_path = self.exports_dir / f".tmp_{periodo.slug}_atividades.jsonl"
            jsonl_path.unlink(missing_ok=True)
            state = ExportState(
                version=STATE_VERSION,
                periodo_inicio=date_from.isoformat(),
                periodo_fim=date_to.isoformat(),
                jsonl_path=str(jsonl_path),
                iniciado_em=datetime.now().isoformat(timespec="seconds"),
            )
            log("INFO", f"iniciando export: {periodo.slug} ({len(janelas)} janelas)")
        else:
            jsonl_path = Path(state.jsonl_path)
            log(
                "INFO",
                f"retomando export {periodo.slug}: {len(state.janelas_concluidas)}/{len(janelas)} janelas concluídas, total parcial={state.total_baixado}",
            )

        inicio_run = time.monotonic()
        total_estimado = state.total_baixado

        try:
            for indice, janela in enumerate(janelas, start=1):
                if stop():
                    raise ExportCancelado()
                if janela.label() in state.janelas_concluidas:
                    continue
                if state.janela_atual and state.janela_atual.label() == janela.label():
                    offset_inicial = state.offset_atual
                else:
                    offset_inicial = 0
                    state.janela_atual = janela
                    state.offset_atual = 0
                    self._salvar_state(state_path, state)

                log(
                    "INFO",
                    f"janela {indice}/{len(janelas)}: {janela.label()} (offset inicial {offset_inicial})",
                )

                janela_total = self._processar_janela(
                    janela=janela,
                    offset_inicial=offset_inicial,
                    state=state,
                    state_path=state_path,
                    jsonl_path=jsonl_path,
                    log=log,
                    emit=emit,
                    stop=stop,
                    janela_indice=indice,
                    janelas_total=len(janelas),
                )
                total_estimado = max(total_estimado, state.total_baixado)
                if janela_total is not None:
                    total_estimado = max(total_estimado, state.total_baixado + (janela_total - (state.offset_atual)))

                state.janelas_concluidas.append(janela.label())
                state.janela_atual = None
                state.offset_atual = 0
                self._salvar_state(state_path, state)

            log("INFO", "todas janelas baixadas — gerando XLSX e CSV")

        except ExportCancelado:
            log("WARN", "export cancelado pelo usuário — state preservado pra retomada")
            raise

        xlsx_path = proximo_caminho_versionado(self.exports_dir, periodo.slug, ".xlsx")
        csv_path = xlsx_path.with_suffix(".csv")
        linhas_xlsx = gerar_xlsx(jsonl_path, xlsx_path)
        linhas_csv = gerar_csv(jsonl_path, csv_path)
        log("INFO", f"gerado {xlsx_path.name} ({linhas_xlsx} linhas) e {csv_path.name} ({linhas_csv} linhas)")

        jsonl_path.unlink(missing_ok=True)
        state_path.unlink(missing_ok=True)

        return ExportResult(
            xlsx_path=xlsx_path,
            csv_path=csv_path,
            total_atividades=linhas_xlsx,
            duracao_segundos=time.monotonic() - inicio_run,
            periodo_inicio=date_from,
            periodo_fim=date_to,
        )

    def _auditar_chaves(self, batch: list[dict], log: LogCallback) -> None:
        """Loga 1 vez por export se aparecerem campos não previstos em CHAVES_ATIVIDADE_CONHECIDAS.

        Útil pra detectar campos que a doc não menciona mas que a API retorna —
        candidatos a entrar em storage.COLUNAS sem precisar abrir o JSONL na mão.
        """
        if self._chaves_logadas or not batch:
            return
        chaves_uniao: set[str] = set()
        for a in batch:
            if isinstance(a, dict):
                chaves_uniao.update(a.keys())
        novas = chaves_uniao - CHAVES_ATIVIDADE_CONHECIDAS
        ausentes = CHAVES_ATIVIDADE_CONHECIDAS - chaves_uniao
        if novas:
            log(
                "WARN",
                f"campos NÃO documentados encontrados na resposta: {sorted(novas)} — considere incluir em storage.COLUNAS",
            )
        if ausentes:
            log(
                "INFO",
                f"campos esperados ausentes neste batch: {sorted(ausentes)} (pode ser normal)",
            )
        self._chaves_logadas = True

    def _processar_janela(
        self,
        *,
        janela: Janela,
        offset_inicial: int,
        state: ExportState,
        state_path: Path,
        jsonl_path: Path,
        log: LogCallback,
        emit: ProgressCallback,
        stop: StopChecker,
        janela_indice: int,
        janelas_total: int,
    ) -> int | None:
        offset = offset_inicial
        total_count: int | None = None

        while True:
            if stop():
                raise ExportCancelado()

            resposta = self.client.list_atividades(
                created_start=janela.inicio,
                created_end=janela.fim,
                limit=PAGE_SIZE,
                offset=offset,
            )

            if not isinstance(resposta, dict):
                raise RuntimeError(
                    f"resposta inesperada de /posts (não-objeto): tipo={type(resposta).__name__}"
                )

            data = resposta.get("data")
            if not isinstance(data, list):
                raise RuntimeError(
                    f"resposta sem campo 'data' (lista) em /posts: chaves={list(resposta.keys())[:10]}"
                )

            if total_count is None:
                total_count = resposta.get("totalCount")
                if isinstance(total_count, int):
                    log("INFO", f"  totalCount da janela {janela.label()}: {total_count}")

            self._auditar_chaves(data, log)

            gravados = gravar_jsonl_append(jsonl_path, data)
            offset += len(data)
            state.offset_atual = offset
            state.total_baixado += gravados
            self._salvar_state(state_path, state)

            emit(
                ExportProgress(
                    janela_label=janela.label(),
                    janela_indice=janela_indice,
                    janelas_total=janelas_total,
                    offset_atual=offset,
                    total_baixado=state.total_baixado,
                    total_estimado=state.total_baixado + max(0, (total_count or 0) - offset)
                    if isinstance(total_count, int)
                    else state.total_baixado,
                    msg=f"{janela.label()}: {offset}/{total_count or '?'}",
                )
            )

            log(
                "DEBUG",
                f"  batch {janela.label()} offset={offset_inicial}..{offset} (+{len(data)}) total_baixado={state.total_baixado}",
            )

            if len(data) < PAGE_SIZE:
                return total_count
            if isinstance(total_count, int) and offset >= total_count:
                return total_count
            offset_inicial = offset
