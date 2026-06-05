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

# Colunas do XLSX/CSV, na ordem. Cada par (header_humano, getter).
COLUNAS: list[tuple[str, str]] = [
    ("ID", "id"),
    ("Data", "date"),
    ("Prazo", "date_deadline"),
    ("Tarefa", "task"),
    ("Recompensa", "reward"),
    ("Observações", "notes"),
    ("Local", "local"),
    ("Processo ID", "lawsuits_id"),
    ("Número do Processo", "_process_number"),
    ("Protocolo", "_protocol_number"),
    ("Cliente(s)", "_clientes"),
    ("Responsável(is)", "_responsaveis"),
    ("Importante", "_importante"),
    ("Urgente", "_urgente"),
    ("Concluída", "_concluida"),
    ("Criada em", "created_at"),
]


def achatar_atividade(atividade: dict[str, Any]) -> dict[str, Any]:
    """Achata uma atividade do /posts em campos planos pra planilha."""
    lawsuit = atividade.get("lawsuit") or {}
    customers = lawsuit.get("customers") or []
    users = atividade.get("users") or []

    return {
        "id": atividade.get("id"),
        "date": atividade.get("date"),
        "date_deadline": atividade.get("date_deadline"),
        "task": atividade.get("task"),
        "reward": atividade.get("reward"),
        "notes": atividade.get("notes"),
        "local": atividade.get("local"),
        "lawsuits_id": atividade.get("lawsuits_id"),
        "created_at": atividade.get("created_at"),
        "_process_number": lawsuit.get("process_number"),
        "_protocol_number": lawsuit.get("protocol_number"),
        "_clientes": " | ".join(c.get("name", "") for c in customers if c.get("name")),
        "_responsaveis": " | ".join(u.get("name", "") for u in users if u.get("name")),
        "_importante": _flag_join(users, "important"),
        "_urgente": _flag_join(users, "urgent"),
        "_concluida": _flag_join(users, "completed"),
    }


def _flag_join(users: list[dict[str, Any]], key: str) -> str:
    valores = [str(u.get(key)) for u in users if u.get(key) is not None]
    return " | ".join(valores)


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

    for col_idx, (header, _) in enumerate(COLUNAS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill

    ws.freeze_panes = "A2"

    row_idx = 2
    for atividade in ler_jsonl(jsonl_path):
        achatada = achatar_atividade(atividade)
        for col_idx, (_, key) in enumerate(COLUNAS, start=1):
            ws.cell(row=row_idx, column=col_idx, value=achatada.get(key))
        row_idx += 1

    # larguras decentes
    larguras = [12, 20, 20, 30, 12, 50, 30, 12, 28, 18, 40, 40, 12, 10, 12, 20]
    for i, w in enumerate(larguras, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

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
