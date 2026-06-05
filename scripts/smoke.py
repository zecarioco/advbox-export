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
    resposta = client.list_atividades(limit=5, offset=0)

    if not isinstance(resposta, dict):
        print(f"ERRO: resposta não é dict (tipo {type(resposta).__name__})")
        print(json.dumps(resposta, indent=2, ensure_ascii=False)[:1000])
        return 2

    print(f"chaves no envelope: {sorted(resposta.keys())}")
    print(f"totalCount         : {resposta.get('totalCount')}")
    print(f"limit              : {resposta.get('limit')}")
    print(f"offset             : {resposta.get('offset')}")
    print(f"len(data)          : {len(resposta.get('data', []))}")
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

    primeira = data[0]
    print("--- primeira atividade (cru) ---")
    print(json.dumps(primeira, indent=2, ensure_ascii=False))
    print()
    print("--- mesma atividade achatada (como vai pro XLSX) ---")
    print(json.dumps(achatar_atividade(primeira), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
