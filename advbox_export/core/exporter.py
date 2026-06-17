from __future__ import annotations

import calendar
import collections
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
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

# A API rejeita offset > 10000 com 422 ("use cursor pagination") e não
# expõe parâmetro de cursor (testado: cursor/after/since_id/starting_after/page
# e mais 8 nomes — todos ignorados). Workaround: se totalCount da janela
# passar disso, subdividir a janela ao meio até cada metade caber.
API_OFFSET_LIMIT = 10000

# Atividades com este `task` são logs internos da AdvBox (exclusões de tarefas).
# Vêm com tudo null (date, lawsuits_id, lawsuit, etc) e não aparecem no painel.
TASK_ALERTA_EXCLUIDA = "ALERTA DE TAREFA EXCLUÍDA"

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
        """Label legível usado pra dedup de janelas concluídas.

        Mês inteiro fechado vira 'YYYY-MM'. Qualquer outra coisa (incluindo
        sub-janelas após split) vira o range completo — caso contrário 2
        sub-janelas do mesmo mês teriam o mesmo label e a 2ª seria pulada.
        """
        if self.inicio == self.fim:
            return self.inicio
        if self.inicio[:7] == self.fim[:7] and self.inicio.endswith("-01"):
            ultimo = calendar.monthrange(int(self.fim[:4]), int(self.fim[5:7]))[1]
            if int(self.fim[8:10]) == ultimo:
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


def _subdividir_janela(janela: Janela) -> list[Janela] | None:
    """Divide uma janela ao meio. Retorna None se já é um único dia."""
    inicio = date.fromisoformat(janela.inicio)
    fim = date.fromisoformat(janela.fim)
    if inicio >= fim:
        return None
    delta_dias = (fim - inicio).days
    meio = inicio + timedelta(days=delta_dias // 2)
    return [
        Janela(inicio=inicio.isoformat(), fim=meio.isoformat()),
        Janela(inicio=(meio + timedelta(days=1)).isoformat(), fim=fim.isoformat()),
    ]


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
        # cache: lawsuit_id -> {(task, start): author}
        self._historico_cache: dict[int, dict[tuple[str, str], str]] = {}
        # cache: lawsuit_id -> {type, group, stage, responsible, ...}
        # Populado uma vez no início do run() via /lawsuits paginado.
        self._lawsuit_cache: dict[int, dict] = {}
        # Flags ativadas pelo caller via `run()`.
        self._incluir_remetente = False
        self._incluir_comentarios = False

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
        incluir_remetente: bool = False,
        incluir_comentarios: bool = False,
    ) -> ExportResult:
        self._incluir_remetente = incluir_remetente
        self._incluir_comentarios = incluir_comentarios
        log = log_cb or (lambda lvl, msg: logger.log(getattr(logging, lvl, logging.INFO), msg))
        emit = progress_cb or (lambda p: None)
        stop = should_stop or (lambda: False)

        self._precarregar_lawsuits(log, stop)

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

        janelas_iniciais = _janelas_mensais(date_from, date_to)

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
            log("INFO", f"iniciando export: {periodo.slug} ({len(janelas_iniciais)} janelas mensais)")
        else:
            jsonl_path = Path(state.jsonl_path)
            # State corrompido (ex: rodada anterior bateu no offset=10000 antes
            # da subdivisão existir): descarta janela_atual pra ela ser
            # re-probed e subdividida.
            if state.offset_atual > API_OFFSET_LIMIT:
                log(
                    "WARN",
                    f"state com offset_atual={state.offset_atual} > {API_OFFSET_LIMIT} "
                    f"(da versão antiga, antes da subdivisão automática) — "
                    f"resetando janela atual pra reprocessar com split",
                )
                state.janela_atual = None
                state.offset_atual = 0
                self._salvar_state(state_path, state)
            log(
                "INFO",
                f"retomando export {periodo.slug}: {len(state.janelas_concluidas)} janelas concluídas, total parcial={state.total_baixado}",
            )

        # Fila de janelas pendentes — subdivisões adicionam novas entradas
        # no início. Janelas já completas (ou em retomada) entram no estado certo.
        fila: collections.deque[Janela] = collections.deque(janelas_iniciais)
        janelas_concluidas_nesta_run = 0

        inicio_run = time.monotonic()

        try:
            while fila:
                if stop():
                    raise ExportCancelado()

                janela = fila.popleft()
                if janela.label() in state.janelas_concluidas:
                    continue

                # Pré-probe: pega totalCount com custo mínimo (limit=1).
                if state.janela_atual and state.janela_atual.label() == janela.label():
                    # Retomada da mesma janela — total já foi descoberto antes.
                    offset_inicial = state.offset_atual
                    janela_total: int | None = None
                else:
                    offset_inicial = 0
                    janela_total = self._probe_total(janela, stop)
                    if janela_total is not None and janela_total > API_OFFSET_LIMIT:
                        sub = _subdividir_janela(janela)
                        if sub is None:
                            log(
                                "ERROR",
                                f"janela {janela.label()} tem {janela_total} atividades "
                                f"(>{API_OFFSET_LIMIT}) e já é de 1 dia — não dá pra dividir mais",
                            )
                            # Tenta processar mesmo assim — a API vai entregar até offset 10000.
                        else:
                            log(
                                "INFO",
                                f"janela {janela.label()} tem {janela_total} atividades "
                                f"(>{API_OFFSET_LIMIT}) — subdividindo em {len(sub)}",
                            )
                            for s in reversed(sub):
                                fila.appendleft(s)
                            continue
                    state.janela_atual = janela
                    state.offset_atual = 0
                    self._salvar_state(state_path, state)

                indice = janelas_concluidas_nesta_run + 1
                janelas_total_estimado = indice + len(fila)
                log(
                    "INFO",
                    f"janela {indice}/{janelas_total_estimado}+: {janela.label()} "
                    f"(total_count={janela_total or '?'}, offset inicial {offset_inicial})",
                )

                self._processar_janela(
                    janela=janela,
                    offset_inicial=offset_inicial,
                    state=state,
                    state_path=state_path,
                    jsonl_path=jsonl_path,
                    log=log,
                    emit=emit,
                    stop=stop,
                    janela_indice=indice,
                    janelas_total=janelas_total_estimado,
                    total_count_conhecido=janela_total,
                )

                state.janelas_concluidas.append(janela.label())
                state.janela_atual = None
                state.offset_atual = 0
                self._salvar_state(state_path, state)
                janelas_concluidas_nesta_run += 1

            log("INFO", "todas janelas baixadas — gerando XLSX e CSV")

        except ExportCancelado:
            log("WARN", "export cancelado pelo usuário — state preservado pra retomada")
            raise

        xlsx_path = proximo_caminho_versionado(self.exports_dir, periodo.slug, ".xlsx")
        csv_path = xlsx_path.with_suffix(".csv")
        linhas_xlsx = gerar_xlsx(
            jsonl_path,
            xlsx_path,
            range_inicio_iso=date_from.isoformat(),
            range_fim_iso=date_to.isoformat(),
        )
        linhas_csv = gerar_csv(
            jsonl_path,
            csv_path,
            range_inicio_iso=date_from.isoformat(),
            range_fim_iso=date_to.isoformat(),
        )
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

    def _enriquecer_com_author(
        self,
        batch: list[dict],
        log: LogCallback,
        stop: StopChecker,
    ) -> None:
        """Injeta __author__ em cada atividade, buscando em /history/{lawsuit_id}.

        Cacheia por lawsuit_id pra não fazer GET repetido. Cada lookup novo
        custa 1 request (e ~2.1s pelo rate limit), então pra 45k tarefas
        distribuídas em N processos únicos, o overhead total ≈ N × 2.1s.

        Checa `stop()` antes de cada lookup pra responder a cancelamento.
        Lookups já feitos ficam preservados no cache pra retomada.
        """
        ids_novos: list[int] = []
        for a in batch:
            lid = a.get("lawsuits_id")
            if isinstance(lid, int) and lid not in self._historico_cache:
                if lid not in ids_novos:
                    ids_novos.append(lid)

        if ids_novos:
            log(
                "INFO",
                f"  buscando histórico de {len(ids_novos)} processo(s) novo(s) "
                f"para preencher Remetente (~{len(ids_novos) * 2.1:.0f}s)",
            )

        for lid in ids_novos:
            if stop():
                raise ExportCancelado()
            try:
                resposta = self.client.get_history(lid)
                self._historico_cache[lid] = self._build_history_map(resposta)
            except Exception as exc:
                log("WARN", f"falha em /history/{lid}: {exc} — Remetente ficará vazio")
                self._historico_cache[lid] = {}

        for a in batch:
            lid = a.get("lawsuits_id")
            if not isinstance(lid, int):
                continue
            cache = self._historico_cache.get(lid, {})
            chave = (a.get("task") or "", a.get("date") or "")
            author = cache.get(chave)
            if author:
                a["__author__"] = author

    def _precarregar_lawsuits(self, log: LogCallback, stop: StopChecker) -> None:
        """Pagina /lawsuits uma vez e popula _lawsuit_cache com o catálogo inteiro.

        Custa ceil(totalCount / PAGE_SIZE) requests (~6s pra um escritório de
        ~2800 processos), em vez de 1 GET por processo único nas atividades.
        Resultado: type/group/stage/responsible disponíveis pra todo lawsuits_id
        sem custo adicional por janela.
        """
        if self._lawsuit_cache:
            return  # já populado (ex: retomada da mesma instância)
        offset = 0
        total: int | None = None
        log("INFO", "pré-carregando catálogo de processos (/lawsuits)…")
        while True:
            if stop():
                raise ExportCancelado()
            try:
                resp = self.client.list_lawsuits(limit=PAGE_SIZE, offset=offset)
            except Exception as exc:
                log("WARN", f"falha em /lawsuits offset={offset}: {exc} — Tipo de ação ficará vazio")
                return
            if not isinstance(resp, dict):
                log("WARN", f"/lawsuits devolveu tipo inesperado em offset={offset} — abortando pré-carga")
                return
            data = resp.get("data") or []
            if not isinstance(data, list):
                log("WARN", f"/lawsuits sem campo 'data' em offset={offset} — abortando pré-carga")
                return
            if total is None:
                total = resp.get("totalCount") if isinstance(resp.get("totalCount"), int) else None
            for item in data:
                if not isinstance(item, dict):
                    continue
                lid = item.get("id")
                if not isinstance(lid, int):
                    continue
                self._lawsuit_cache[lid] = {
                    "type": item.get("type") or "",
                    "group": item.get("group") or "",
                    "stage": item.get("stage") or "",
                    "responsible": item.get("responsible") or "",
                }
            if len(data) < PAGE_SIZE:
                break
            if isinstance(total, int) and offset + len(data) >= total:
                break
            offset += len(data)
        log("INFO", f"  catálogo carregado: {len(self._lawsuit_cache)} processo(s)")

    def _aplicar_lawsuit_extra(self, batch: list[dict]) -> None:
        """Injeta __lawsuit_extra__ a partir do cache pré-carregado."""
        for a in batch:
            lid = a.get("lawsuits_id")
            if not isinstance(lid, int):
                continue
            extra = self._lawsuit_cache.get(lid)
            if extra:
                a["__lawsuit_extra__"] = extra

    @staticmethod
    def _build_history_map(resposta: object) -> dict[tuple[str, str], str]:
        """Constrói {(task, start): author} a partir da resposta do /history."""
        if not isinstance(resposta, dict):
            return {}
        items = resposta.get("data") or []
        if not isinstance(items, list):
            return {}
        mapa: dict[tuple[str, str], str] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            author = item.get("author")
            if not author:
                continue
            chave = (item.get("task") or "", item.get("start") or "")
            mapa[chave] = author
        return mapa

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

    def _probe_total(self, janela: Janela, stop: StopChecker) -> int | None:
        """Lê totalCount da janela com 1 request mínimo (limit=1).

        Custa ~2.1s (1 GET respeitando o throttle), mas é o único modo de
        decidir se precisa subdividir antes de bater no offset > 10000.
        """
        if stop():
            raise ExportCancelado()
        try:
            r = self.client.list_atividades(
                completed_start=janela.inicio,
                completed_end=janela.fim,
                limit=1,
                offset=0,
            )
        except Exception:
            return None
        if not isinstance(r, dict):
            return None
        tc = r.get("totalCount")
        return tc if isinstance(tc, int) else None

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
        total_count_conhecido: int | None = None,
    ) -> int | None:
        offset = offset_inicial
        total_count: int | None = total_count_conhecido
        if total_count is not None:
            log("INFO", f"  totalCount da janela {janela.label()}: {total_count}")

        while True:
            if stop():
                raise ExportCancelado()

            resposta = self.client.list_atividades(
                completed_start=janela.inicio,
                completed_end=janela.fim,
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

            total_recebido = len(data)
            data_filtrada = [
                a for a in data if a.get("task") != TASK_ALERTA_EXCLUIDA
            ]
            descartadas_alerta = total_recebido - len(data_filtrada)
            if descartadas_alerta:
                log(
                    "INFO",
                    f"  descartadas {descartadas_alerta} entrada(s) de '{TASK_ALERTA_EXCLUIDA}'",
                )

            if not self._incluir_comentarios:
                antes = len(data_filtrada)
                # Painel descarta APENAS reward=0 (comentários internos auto).
                # Mantém positivos (recompensa) e negativos (penalidade por atraso —
                # ex: LAUDO EM ATRASO reward=-100).
                data_filtrada = [
                    a for a in data_filtrada if (a.get("reward") or 0) != 0
                ]
                descartadas_comentario = antes - len(data_filtrada)
                if descartadas_comentario:
                    log(
                        "INFO",
                        f"  descartadas {descartadas_comentario} entrada(s) sem pontuação "
                        f"(comentários internos — marque 'Incluir comentários' pra incluir)",
                    )

            self._aplicar_lawsuit_extra(data_filtrada)
            if self._incluir_remetente:
                self._enriquecer_com_author(data_filtrada, log, stop)

            gravados = gravar_jsonl_append(jsonl_path, data_filtrada)
            offset += total_recebido  # offset segue baseado no que a API entregou
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
