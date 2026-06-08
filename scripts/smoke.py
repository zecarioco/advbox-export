"""Smoke test rápido contra a API real.

Roda 1 GET /posts?limit=5 (sem filtro), imprime totalCount, chaves recebidas
vs esperadas, e o JSON achatado da primeira atividade. Útil pra calibrar
storage.COLUNAS antes do primeiro export grande.

Uso:
    .venv/bin/python scripts/smoke.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from advbox_export.core.client import AdvboxClient  # noqa: E402
from advbox_export.core.config import ConfigStore  # noqa: E402
from advbox_export.core.exporter import CHAVES_ATIVIDADE_CONHECIDAS  # noqa: E402
from advbox_export.core.paths import config_file  # noqa: E402
from advbox_export.core.storage import achatar_atividade  # noqa: E402


def main() -> int:
    cfg = ConfigStore(config_file()).load()
    if not cfg.token:
        print("ERRO: nenhum token encontrado em .env nem em config.json")
        return 1

    print(f"base_url = {cfg.base_url}")
    print(f"token    = {cfg.token[:6]}…{cfg.token[-4:]} ({len(cfg.token)} chars)")
    print()

    client = AdvboxClient(token=cfg.token, base_url=cfg.base_url)
    # Filtra por maio/2025 — período da planilha do painel que tem atividades
    # reais com hora marcada (ex: AGENDAR REUNIÃO 17:00). Sem filtro, o offset 0
    # vem dominado por "ALERTA DE TAREFA EXCLUÍDA" recentes.
    resposta = client.list_atividades(
        limit=1000,
        offset=0,
        created_start="2025-05-01",
        created_end="2025-05-31",
    )

    if not isinstance(resposta, dict):
        print(f"ERRO: resposta não é dict (tipo {type(resposta).__name__})")
        print(json.dumps(resposta, indent=2, ensure_ascii=False)[:1000])
        return 2

    print(f"chaves no envelope: {sorted(resposta.keys())}")
    print(f"totalCount         : {resposta.get('totalCount')}")
    print(f"limit              : {resposta.get('limit')}")
    print(f"offset             : {resposta.get('offset')}")
    print(f"len(data)          : {len(resposta.get('data', []))}")
    if "query" in resposta:
        print(f"query              : {json.dumps(resposta['query'], ensure_ascii=False)[:300]}")
    print()

    data = resposta.get("data", [])
    if not data:
        print("(nenhuma atividade retornada — conta vazia?)")
        return 0

    chaves_uniao: set[str] = set()
    for a in data:
        if isinstance(a, dict):
            chaves_uniao.update(a.keys())

    novas = sorted(chaves_uniao - CHAVES_ATIVIDADE_CONHECIDAS)
    ausentes = sorted(CHAVES_ATIVIDADE_CONHECIDAS - chaves_uniao)
    print(f"campos novos (não documentados): {novas}")
    print(f"campos esperados ausentes      : {ausentes}")
    print()

    # Filtra atividades reais (descarta "ALERTA DE TAREFA EXCLUÍDA" e similares com date null)
    reais = [a for a in data if a.get("date")]
    print(f"--- {len(reais)} atividades REAIS (de {len(data)}, descartando date=null/excluídas) ---")
    print()

    # --- distribuição de horas no campo `date` ---
    from collections import Counter
    horas = Counter()
    horas_nao_zero_exemplos: list[dict] = []
    for a in reais:
        d = a.get("date") or ""
        if " " in d:
            hora = d.split(" ", 1)[1][:5]
        elif "T" in d:
            hora = d.split("T", 1)[1][:5]
        else:
            hora = ""
        horas[hora] += 1
        if hora and hora != "00:00" and len(horas_nao_zero_exemplos) < 5:
            horas_nao_zero_exemplos.append({
                "id": a.get("id"),
                "date": a.get("date"),
                "task": a.get("task"),
            })

    print("--- distribuição de horas no campo `date` (atividades reais) ---")
    for hora, n in horas.most_common(10):
        print(f"  {hora!r}: {n}")
    print()
    if horas_nao_zero_exemplos:
        print(f"--- {len(horas_nao_zero_exemplos)} exemplos de atividade com hora real ---")
        for ex in horas_nao_zero_exemplos:
            print(f"  id={ex['id']}, date={ex['date']!r}, task={ex['task']!r}")
    else:
        print("(NENHUMA das atividades reais teve hora não-zero em `date`)")
    print()

    if not reais:
        return 0
    primeira = reais[0]
    print("--- primeira atividade (cru) ---")
    print(json.dumps(primeira, indent=2, ensure_ascii=False))
    print()
    print("--- mesma atividade achatada (como vai pro XLSX) ---")
    print(json.dumps(achatar_atividade(primeira), indent=2, ensure_ascii=False))
    print()

    # --- audit do /settings pra ver se há campos não documentados em tasks[] ---
    print("--- audit empírico /settings ---")
    try:
        settings = client._get("/settings", {})
    except Exception as exc:
        print(f"(falha ao buscar /settings: {exc})")
        return 0
    if isinstance(settings, dict):
        print(f"top-level keys: {sorted(settings.keys())}")
        tasks_list = settings.get("tasks") or []
        if tasks_list:
            print(f"tasks[]: {len(tasks_list)} entradas. Chaves da primeira: {sorted(tasks_list[0].keys())}")
            print("Primeira task (cru):")
            print(json.dumps(tasks_list[0], indent=2, ensure_ascii=False))
            # Procurar uma task com campos extras
            chaves_uniao = set()
            for t in tasks_list:
                if isinstance(t, dict):
                    chaves_uniao.update(t.keys())
            extras = chaves_uniao - {"id", "task", "reward"}
            if extras:
                print(f"campos NÃO documentados em tasks[]: {sorted(extras)}")
                # mostrar uma task com extras
                for t in tasks_list:
                    if any(k in t for k in extras):
                        print("exemplo com campos extras:")
                        print(json.dumps(t, indent=2, ensure_ascii=False))
                        break
    return 0


if __name__ == "__main__":
    sys.exit(main())
