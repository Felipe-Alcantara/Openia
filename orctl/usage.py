"""Consulta de uso/saldo da conta no OpenRouter.

Usado tanto para mostrar o gasto dentro do menu quanto para alimentar a
statusline do Claude Code. Consulta ``/api/v1/credits``, que devolve o total de
créditos e o total já consumido na conta da chave informada.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

CREDITS_URL = "https://openrouter.ai/api/v1/credits"


class UsageError(RuntimeError):
    """Falha ao consultar o uso no OpenRouter."""


@dataclass(frozen=True)
class Usage:
    """Saldo da conta no OpenRouter (valores em US$)."""

    total_credits: float
    total_usage: float

    @property
    def remaining(self) -> float:
        return self.total_credits - self.total_usage


def fetch_usage(api_key: str, timeout: float = 10.0) -> Usage:
    """Busca uso/saldo no OpenRouter. Levanta ``UsageError`` em falha."""
    if not api_key:
        raise UsageError("chave do OpenRouter ausente.")
    req = urllib.request.Request(
        CREDITS_URL,
        headers={"Authorization": f"Bearer {api_key}", "User-Agent": "orctl"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (URL fixa, https)
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise UsageError(f"não foi possível consultar o uso: {exc}") from exc

    data = payload.get("data") or {}
    try:
        return Usage(
            total_credits=float(data.get("total_credits", 0) or 0),
            total_usage=float(data.get("total_usage", 0) or 0),
        )
    except (TypeError, ValueError) as exc:
        raise UsageError("resposta de uso em formato inesperado.") from exc


def format_line(usage: Usage) -> str:
    """Linha curta de uma só fileira, adequada para statusline/menu."""
    return (
        f"OpenRouter  usado ${usage.total_usage:.4f}"
        f"  ·  resta ${usage.remaining:.2f}"
        f"  (de ${usage.total_credits:.2f})"
    )
