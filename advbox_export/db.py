from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS exports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    criado_em TEXT NOT NULL,
    periodo_inicio TEXT NOT NULL,
    periodo_fim TEXT NOT NULL,
    nome TEXT,
    status TEXT NOT NULL,
    total_registros INTEGER,
    caminho_xlsx TEXT,
    caminho_csv TEXT,
    caminho_log TEXT,
    duracao_segundos REAL,
    erro_mensagem TEXT,
    finalizado_em TEXT
);

CREATE INDEX IF NOT EXISTS idx_exports_criado_em ON exports(criado_em DESC);
"""

STATUS_EM_ANDAMENTO = "em_andamento"
STATUS_CONCLUIDO = "concluido"
STATUS_FALHADO = "falhado"
STATUS_CANCELADO = "cancelado"


@dataclass
class ExportRow:
    id: int
    criado_em: str
    periodo_inicio: str
    periodo_fim: str
    status: str
    total_registros: Optional[int]
    caminho_xlsx: Optional[str]
    caminho_csv: Optional[str]
    caminho_log: Optional[str]
    duracao_segundos: Optional[float]
    erro_mensagem: Optional[str]
    finalizado_em: Optional[str]
    nome: Optional[str] = None


class ExportRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(SCHEMA)
            self._migrate(conn)

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """ALTER TABLE pra colunas adicionadas após v0.1 (sqlite não tem IF NOT EXISTS pra ADD COLUMN)."""
        cols = {r[1] for r in conn.execute("PRAGMA table_info(exports)").fetchall()}
        if "nome" not in cols:
            conn.execute("ALTER TABLE exports ADD COLUMN nome TEXT")

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def criar(self, periodo_inicio: str, periodo_fim: str, nome: str) -> int:
        agora = datetime.now().isoformat(timespec="seconds")
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO exports (criado_em, periodo_inicio, periodo_fim, nome, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (agora, periodo_inicio, periodo_fim, nome, STATUS_EM_ANDAMENTO),
            )
            return int(cur.lastrowid)

    def marcar_concluido(
        self,
        export_id: int,
        *,
        caminho_xlsx: str,
        caminho_csv: str,
        caminho_log: str | None,
        total_registros: int,
        duracao_segundos: float,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE exports SET
                    status = ?,
                    caminho_xlsx = ?,
                    caminho_csv = ?,
                    caminho_log = ?,
                    total_registros = ?,
                    duracao_segundos = ?,
                    finalizado_em = ?
                WHERE id = ?
                """,
                (
                    STATUS_CONCLUIDO,
                    caminho_xlsx,
                    caminho_csv,
                    caminho_log,
                    total_registros,
                    duracao_segundos,
                    datetime.now().isoformat(timespec="seconds"),
                    export_id,
                ),
            )

    def marcar_falhado(
        self,
        export_id: int,
        *,
        erro_mensagem: str,
        caminho_log: str | None = None,
        total_parcial: int | None = None,
        duracao_segundos: float | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE exports SET
                    status = ?,
                    erro_mensagem = ?,
                    caminho_log = COALESCE(?, caminho_log),
                    total_registros = COALESCE(?, total_registros),
                    duracao_segundos = COALESCE(?, duracao_segundos),
                    finalizado_em = ?
                WHERE id = ?
                """,
                (
                    STATUS_FALHADO,
                    erro_mensagem,
                    caminho_log,
                    total_parcial,
                    duracao_segundos,
                    datetime.now().isoformat(timespec="seconds"),
                    export_id,
                ),
            )

    def marcar_cancelado(
        self,
        export_id: int,
        *,
        caminho_log: str | None = None,
        total_parcial: int | None = None,
        duracao_segundos: float | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE exports SET
                    status = ?,
                    caminho_log = COALESCE(?, caminho_log),
                    total_registros = COALESCE(?, total_registros),
                    duracao_segundos = COALESCE(?, duracao_segundos),
                    finalizado_em = ?
                WHERE id = ?
                """,
                (
                    STATUS_CANCELADO,
                    caminho_log,
                    total_parcial,
                    duracao_segundos,
                    datetime.now().isoformat(timespec="seconds"),
                    export_id,
                ),
            )

    def listar(self, *, limite: int = 100) -> list[ExportRow]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM exports ORDER BY criado_em DESC, id DESC LIMIT ?
                """,
                (limite,),
            ).fetchall()
        return [ExportRow(**dict(row)) for row in rows]

    def obter(self, export_id: int) -> ExportRow | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM exports WHERE id = ?", (export_id,)
            ).fetchone()
        return ExportRow(**dict(row)) if row else None

    def remover(self, export_id: int) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM exports WHERE id = ?", (export_id,))
