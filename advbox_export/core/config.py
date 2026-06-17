from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASE_URL = "https://app.advbox.com.br/api/v1"


VALID_THEMES = ("light", "dark")


@dataclass
class Config:
    token: str = ""
    base_url: str = DEFAULT_BASE_URL
    theme: str = "light"
    # None = exporta todos os destinatários. Lista de nomes = filtra somente esses
    # (replica o "filtro de equipe" do painel da AdvBox, que não é exposto pela API).
    usuarios_filtrados: list[str] | None = None

    def to_dict(self) -> dict:
        d: dict = {"token": self.token, "base_url": self.base_url, "theme": self.theme}
        if self.usuarios_filtrados is not None:
            d["usuarios_filtrados"] = list(self.usuarios_filtrados)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Config":
        theme = d.get("theme") or "light"
        if theme not in VALID_THEMES:
            theme = "light"
        raw_filtros = d.get("usuarios_filtrados")
        if isinstance(raw_filtros, list):
            filtros: list[str] | None = [str(x) for x in raw_filtros if isinstance(x, str)]
        else:
            filtros = None
        return cls(
            token=d.get("token", "") or "",
            base_url=d.get("base_url") or DEFAULT_BASE_URL,
            theme=theme,
            usuarios_filtrados=filtros,
        )


class ConfigStore:
    """Lê/grava config.json no path informado.

    Variáveis de ambiente (ADVBOX_TOKEN, ADVBOX_BASE_URL) têm precedência ao ler
    — útil em dev com .env. Em produção (binário), o arquivo manda.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> Config:
        cfg = self._load_from_file()
        token_env = os.environ.get("ADVBOX_TOKEN", "").strip()
        base_url_env = os.environ.get("ADVBOX_BASE_URL", "").strip()
        if token_env:
            cfg.token = token_env
        if base_url_env:
            cfg.base_url = base_url_env
        return cfg

    def _load_from_file(self) -> Config:
        if not self.path.exists():
            return Config()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return Config()
        if not isinstance(raw, dict):
            return Config()
        return Config.from_dict(raw)

    def save(self, cfg: Config) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def is_configured(self) -> bool:
        return bool(self.load().token)
