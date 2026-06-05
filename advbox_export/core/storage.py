from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

# Espelha as colunas do export do painel AdvBox.
COLUNAS: list[tuple[str, str]] = [
    ("Prioridade", "_prioridade"),
    ("Data", "_data"),
    ("Hora", "_hora"),
    ("Término", "_termino_data"),
    ("Hora Término", "_termino_hora"),
    ("Prazo fatal", "_prazo_fatal"),
    ("Data Conclusão", "_data_conclusao"),
    ("Pontuação", "reward"),
    ("Compromisso", "task"),
    ("Local", "local"),
    ("Remetente", "_remetente"),
    ("Destinatário", "_destinatario"),
    ("Partes", "_partes"),
    ("Processo (CNJ)", "_process_number"),
    ("Protocolo", "_protocol_number"),
    ("Tipo de ação", "_tipo_acao"),
    ("Observações", "notes"),
]

# Ocultas no XLSX, fora do CSV. Servem pra você inspecionar atividades
# atípicas sem precisar abrir o JSONL bruto.
COLUNAS_DEBUG_XLSX: list[tuple[str, str]] = [
    ("ID", "id"),
    ("Atividade (JSON bruto)", "_raw_atividade"),
    ("Lawsuit (JSON bruto)", "_raw_lawsuit"),
]


_PRIORIDADES = {0: "BAIXA", 1: "NORMAL", 2: "ALTA", 3: "URGENTE"}


def achatar_atividade(atividade: dict[str, Any]) -> dict[str, Any]:
    """Achata uma atividade do /posts pros 17 campos do export do painel."""
    lawsuit = atividade.get("lawsuit") or {}
    customers = lawsuit.get("customers") or []
    users = atividade.get("users") or []

    data, hora = _split_datetime(atividade.get("date"))
    fim_data, fim_hora = _split_datetime(
        atividade.get("end_date") or atividade.get("date_end")
    )
    return {
        "id": atividade.get("id"),
        "_prioridade": _resolver_prioridade(atividade, users),
        "_data": data,
        "_hora": hora,
        "_termino_data": fim_data,
        "_termino_hora": fim_hora,
        "_prazo_fatal": _formatar_data(atividade.get("date_deadline")),
        "_data_conclusao": _resolver_data_conclusao(atividade, users),
        "reward": atividade.get("reward"),
        "task": atividade.get("task"),
        "local": atividade.get("local"),
        "_remetente": _resolver_remetente(atividade),
        "_destinatario": ", ".join(u.get("name", "") for u in users if u.get("name")),
        "_partes": ", ".join(c.get("name", "") for c in customers if c.get("name")),
        "_process_number": lawsuit.get("process_number"),
        "_protocol_number": lawsuit.get("protocol_number"),
        "_tipo_acao": _primeiro_nao_nulo(
            atividade.get("tipo_acao"),
            atividade.get("task_type"),
            atividade.get("category"),
            (atividade.get("type") or {}).get("name") if isinstance(atividade.get("type"), dict) else atividade.get("type"),
        ),
        "notes": atividade.get("notes"),
        "_raw_atividade": json.dumps(atividade, ensure_ascii=False),
        "_raw_lawsuit": json.dumps(lawsuit, ensure_ascii=False) if lawsuit else "",
    }


def _split_datetime(raw: Any) -> tuple[str, str]:
    """'2025-05-12 17:00:00' -> ('12/05/2025', '17:00'). Aceita também só data."""
    if not raw or not isinstance(raw, str):
        return "", ""
    raw = raw.strip()
    parte_data, _, parte_hora = raw.partition(" ")
    if not parte_hora:
        parte_data, _, parte_hora = raw.partition("T")
    data_fmt = _formatar_data(parte_data)
    hora_fmt = parte_hora[:5] if parte_hora else ""
    return data_fmt, hora_fmt


def _formatar_data(raw: Any) -> str:
    """'2025-05-12' ou '2025-05-12 17:00:00' -> '12/05/2025'."""
    if not raw or not isinstance(raw, str):
        return ""
    parte_data = raw[:10]
    if len(parte_data) == 10 and parte_data[4] == "-" and parte_data[7] == "-":
        return f"{parte_data[8:10]}/{parte_data[5:7]}/{parte_data[0:4]}"
    return raw


def _resolver_prioridade(atividade: dict[str, Any], users: list[dict[str, Any]]) -> str:
    """Prioridade: tenta campo top-level, depois deriva das flags important/urgent."""
    raw = atividade.get("priority")
    if isinstance(raw, str) and raw:
        return raw.upper()
    if isinstance(raw, int) and raw in _PRIORIDADES:
        return _PRIORIDADES[raw]
    urgentes = sum(1 for u in users if u.get("urgent"))
    importantes = sum(1 for u in users if u.get("important"))
    if urgentes:
        return "URGENTE"
    if importantes:
        return "ALTA"
    return "NORMAL"


def _resolver_data_conclusao(
    atividade: dict[str, Any], users: list[dict[str, Any]]
) -> str:
    """Tenta campos top-level; senão pega o primeiro `users[].completed` parseável."""
    for chave in ("completed_at", "completed_date", "date_completed"):
        valor = atividade.get(chave)
        if valor:
            return _formatar_datetime(valor)
    for u in users:
        c = u.get("completed")
        if c and isinstance(c, str) and len(c) >= 10:
            return _formatar_datetime(c)
    return ""


def _formatar_datetime(raw: str) -> str:
    """'2025-05-12 08:10:00' -> '12/05/2025 08:10'."""
    data, hora = _split_datetime(raw)
    if data and hora:
        return f"{data} {hora}"
    return data or hora or raw


def _resolver_remetente(atividade: dict[str, Any]) -> str:
    """Tenta vários campos comuns pra autor/criador. Vazio se nada bater."""
    candidatos = (
        atividade.get("sender"),
        atividade.get("from"),
        atividade.get("created_by_name"),
        atividade.get("creator"),
        atividade.get("user_name"),
    )
    for c in candidatos:
        if isinstance(c, str) and c:
            return c
        if isinstance(c, dict):
            nome = c.get("name") or c.get("nome")
            if nome:
                return nome
    return ""


def _primeiro_nao_nulo(*valores: Any) -> str:
    for v in valores:
        if v not in (None, ""):
            return str(v)
    return ""


def gravar_jsonl_append(path: Path, atividades: Iterable[dict[str, Any]]) -> int:
    """Append atividades brutas (1 por linha) no JSONL. Retorna quantas gravou."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8") as f:
        for a in atividades:
            f.write(json.dumps(a, ensure_ascii=False) + "\n")
            count += 1
    return count


def ler_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if linha:
                yield json.loads(linha)


def gerar_xlsx(jsonl_path: Path, xlsx_path: Path) -> int:
    """Lê o JSONL e escreve XLSX achatado. Retorna número de linhas escritas."""
    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Atividades"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="2E5BBA")

    colunas_xlsx = COLUNAS + COLUNAS_DEBUG_XLSX

    for col_idx, (header, _) in enumerate(colunas_xlsx, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill

    ws.freeze_panes = "A2"

    row_idx = 2
    for atividade in ler_jsonl(jsonl_path):
        achatada = achatar_atividade(atividade)
        for col_idx, (_, key) in enumerate(colunas_xlsx, start=1):
            ws.cell(row=row_idx, column=col_idx, value=achatada.get(key))
        row_idx += 1

    larguras_visiveis = [
        12,  # Prioridade
        12,  # Data
        10,  # Hora
        12,  # Término
        14,  # Hora Término
        14,  # Prazo fatal
        20,  # Data Conclusão
        12,  # Pontuação
        36,  # Compromisso
        18,  # Local
        28,  # Remetente
        28,  # Destinatário
        36,  # Partes
        26,  # Processo (CNJ)
        18,  # Protocolo
        26,  # Tipo de ação
        48,  # Observações
    ]
    larguras_debug = [12, 80, 80]  # ID, Atividade bruta, Lawsuit bruto
    for i, w in enumerate(larguras_visiveis + larguras_debug, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # colunas de debug: largas (caso desoculte) e ocultas por padrão
    primeira_debug = len(COLUNAS) + 1
    for i in range(primeira_debug, primeira_debug + len(COLUNAS_DEBUG_XLSX)):
        col_letter = get_column_letter(i)
        ws.column_dimensions[col_letter].width = 80
        ws.column_dimensions[col_letter].hidden = True

    wb.save(xlsx_path)
    return row_idx - 2


def gerar_csv(jsonl_path: Path, csv_path: Path) -> int:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    headers = [h for h, _ in COLUNAS]
    keys = [k for _, k in COLUNAS]

    count = 0
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for atividade in ler_jsonl(jsonl_path):
            achatada = achatar_atividade(atividade)
            writer.writerow([achatada.get(k, "") for k in keys])
            count += 1
    return count


@dataclass(frozen=True)
class PeriodoArquivo:
    slug: str  # ex: "2026-06" ou "2024-01_2026-06"
    inicio: date
    fim: date


def slug_periodo(inicio: date, fim: date) -> str:
    """Slug curto pro nome do arquivo.

    Mês fechado: '2026-06'. Range cruzando meses: '2024-01_2026-06'.
    """
    if inicio.year == fim.year and inicio.month == fim.month:
        return f"{inicio:%Y-%m}"
    return f"{inicio:%Y-%m}_{fim:%Y-%m}"


def proximo_caminho_versionado(diretorio: Path, slug: str, sufixo: str) -> Path:
    """Devolve exports/{slug}_atividades.{ext} ou _v2, _v3 se já existir."""
    diretorio.mkdir(parents=True, exist_ok=True)
    base = f"{slug}_atividades"
    candidato = diretorio / f"{base}{sufixo}"
    if not candidato.exists():
        return candidato
    n = 2
    while True:
        candidato = diretorio / f"{base}_v{n}{sufixo}"
        if not candidato.exists():
            return candidato
        n += 1
