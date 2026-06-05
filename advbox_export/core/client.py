from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import requests

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://app.advbox.com.br/api/v1"
DEFAULT_TIMEOUT_SECONDS = 30.0

# Rate limit oficial: 30 GET/min = 1 req a cada 2s. 2.1s dá margem pra clock skew.
MIN_INTERVAL_SECONDS = 2.1

# A doc não menciona Retry-After. Espera fixa em 429.
RATE_LIMIT_SLEEP_FALLBACK_SECONDS = 60.0
MAX_RETRIES_RATE_LIMIT = 5
MAX_RETRIES_SERVER_ERROR = 3


class AdvboxError(Exception):
    pass


class AdvboxAuthError(AdvboxError):
    pass


class AdvboxRateLimitError(AdvboxError):
    pass


@dataclass
class AdvboxClient:
    token: str
    base_url: str = DEFAULT_BASE_URL
    timeout: float = DEFAULT_TIMEOUT_SECONDS

    _session: requests.Session = field(init=False, repr=False)
    _last_request_at: float = field(init=False, default=0.0, repr=False)

    def __post_init__(self) -> None:
        if not self.token:
            raise AdvboxAuthError("token AdvBox ausente")
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "User-Agent": "advbox-export/0.1.0",
            }
        )

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        wait = MIN_INTERVAL_SECONDS - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()

    def _get(self, path: str, params: dict[str, Any]) -> Any:
        url = f"{self.base_url.rstrip('/')}{path}"
        rate_attempts = 0
        server_attempts = 0

        while True:
            self._throttle()
            logger.debug("GET %s params=%s", url, params)
            try:
                response = self._session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                raise AdvboxError(f"falha de rede em GET {path}: {exc}") from exc

            status = response.status_code
            self._log_rate_limit_headers(response)

            if status == 200:
                try:
                    return response.json()
                except ValueError as exc:
                    raise AdvboxError(f"resposta não-JSON em GET {path}: {exc}") from exc

            if status in (401, 403):
                raise AdvboxAuthError(
                    f"não autorizado ({status}) em GET {path} — verifique o token"
                )

            if status == 429:
                rate_attempts += 1
                if rate_attempts > MAX_RETRIES_RATE_LIMIT:
                    raise AdvboxRateLimitError(
                        f"429 persistente em GET {path} após {MAX_RETRIES_RATE_LIMIT} tentativas"
                    )
                wait = self._retry_after_seconds(response)
                logger.warning(
                    "429 em %s — dormindo %.0fs (tentativa %d/%d, %s)",
                    path,
                    wait,
                    rate_attempts,
                    MAX_RETRIES_RATE_LIMIT,
                    "Retry-After do servidor" if response.headers.get("Retry-After") else "fallback fixo",
                )
                time.sleep(wait)
                continue

            if 500 <= status < 600:
                server_attempts += 1
                if server_attempts > MAX_RETRIES_SERVER_ERROR:
                    raise AdvboxError(
                        f"erro de servidor {status} persistente em GET {path}"
                    )
                wait = 2 ** server_attempts
                logger.warning(
                    "%d em %s — retry em %ds (tentativa %d/%d)",
                    status,
                    path,
                    wait,
                    server_attempts,
                    MAX_RETRIES_SERVER_ERROR,
                )
                time.sleep(wait)
                continue

            raise AdvboxError(
                f"erro HTTP {status} em GET {path}: {response.text[:300]}"
            )

    @staticmethod
    def _retry_after_seconds(response: requests.Response) -> float:
        """Lê Retry-After do response. Aceita segundos (int) ou HTTP-date.
        Cai pro fallback fixo se ausente ou inválido.
        """
        raw = response.headers.get("Retry-After")
        if not raw:
            return RATE_LIMIT_SLEEP_FALLBACK_SECONDS
        raw = raw.strip()
        try:
            segundos = float(raw)
            if segundos < 0:
                return RATE_LIMIT_SLEEP_FALLBACK_SECONDS
            # capa em 5 min pra não travar o app horas se o servidor mandar algo absurdo
            return min(segundos, 300.0)
        except ValueError:
            return RATE_LIMIT_SLEEP_FALLBACK_SECONDS

    @staticmethod
    def _log_rate_limit_headers(response: requests.Response) -> None:
        """Loga headers de rate limit se aparecerem — a doc não menciona,
        mas APIs costumam mandar mesmo assim. Útil pra calibrar throttling depois.
        """
        interessantes = [
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
            "RateLimit-Limit",
            "RateLimit-Remaining",
            "RateLimit-Reset",
            "Retry-After",
        ]
        achados = {h: response.headers[h] for h in interessantes if h in response.headers}
        if achados:
            logger.debug("rate-limit headers: %s", achados)

    def list_atividades(
        self,
        *,
        created_start: str | None = None,
        created_end: str | None = None,
        date_start: str | None = None,
        date_end: str | None = None,
        deadline_start: str | None = None,
        deadline_end: str | None = None,
        completed_start: str | None = None,
        completed_end: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> Any:
        """Lista atividades (GET /posts).

        Datas em YYYY-MM-DD. A API exige PAR completo de cada filtro de data;
        passar só uma das pontas faz a API ignorar o filtro inteiro.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}

        date_pairs = (
            ("created_start", created_start, "created_end", created_end),
            ("date_start", date_start, "date_end", date_end),
            ("deadline_start", deadline_start, "deadline_end", deadline_end),
            ("completed_start", completed_start, "completed_end", completed_end),
        )
        for start_key, start_val, end_key, end_val in date_pairs:
            if start_val and end_val:
                params[start_key] = start_val
                params[end_key] = end_val
            elif bool(start_val) ^ bool(end_val):
                raise ValueError(
                    f"par {start_key}/{end_key} incompleto — a API ignora se vier só uma ponta"
                )

        return self._get("/posts", params)

    def get_history(self, lawsuit_id: int, status: str | None = None) -> Any:
        """GET /history/{lawsuit_id} — retorna tarefas com author/responsible.

        Útil pra cruzar com /posts e preencher Remetente. status="all" (default),
        "pending" ou "completed". A API ignora limit/offset aqui.
        """
        params: dict[str, Any] = {}
        if status:
            params["status"] = status
        return self._get(f"/history/{lawsuit_id}", params)
