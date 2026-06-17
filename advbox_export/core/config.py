from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_BASE_URL = "https://app.advbox.com.br/api/v1"


VALID_THEMES = ("light", "dark")


@dataclass
class Config:
    token: str = ""
    base_url: str = DEFAULT_BASE_URL
    theme: str = "light"
    # Grupos cadastrados pelo usuário pra simular o "filtro de equipe" do painel
    # (a API não expõe grupos publicamente). Formato: {nome_grupo: [nome_user, ...]}.
    grupos: dict[str, list[str]] = field(default_factory=dict)
    # Seleção que define quem entra no próximo export. União dos dois aplica-se
    # como filtro de Destinatário. Ambas vazias = sem filtro (todos os users).
    grupos_selecionados: list[str] = field(default_factory=list)
    pessoas_selecionadas: list[str] = field(default_factory=list)

    def usuarios_efetivos(self) -> set[str] | None:
        """Resolve a seleção atual em um set de nomes. None = sem filtro."""
        if not self.grupos_selecionados and not self.pessoas_selecionadas:
            return None
        nomes: set[str] = set(self.pessoas_selecionadas)
        for g in self.grupos_selecionados:
            nomes.update(self.grupos.get(g, []))
        return nomes

    def to_dict(self) -> dict:
        d: dict = {"token": self.token, "base_url": self.base_url, "theme": self.theme}
        if self.grupos:
            d["grupos"] = {nome: list(ms) for nome, ms in self.grupos.items()}
        if self.grupos_selecionados:
            d["grupos_selecionados"] = list(self.grupos_selecionados)
        if self.pessoas_selecionadas:
            d["pessoas_selecionadas"] = list(self.pessoas_selecionadas)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Config":
        theme = d.get("theme") or "light"
        if theme not in VALID_THEMES:
            theme = "light"

        raw_grupos = d.get("grupos")
        grupos: dict[str, list[str]] = {}
        if isinstance(raw_grupos, dict):
            for nome, membros in raw_grupos.items():
                if isinstance(nome, str) and isinstance(membros, list):
                    grupos[nome] = [str(m) for m in membros if isinstance(m, str)]

        def _list_str(key: str) -> list[str]:
            raw = d.get(key)
            return [str(x) for x in raw if isinstance(x, str)] if isinstance(raw, list) else []

        return cls(
            token=d.get("token", "") or "",
            base_url=d.get("base_url") or DEFAULT_BASE_URL,
            theme=theme,
            grupos=grupos,
            grupos_selecionados=_list_str("grupos_selecionados"),
            pessoas_selecionadas=_list_str("pessoas_selecionadas"),
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
