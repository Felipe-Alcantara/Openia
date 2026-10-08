"""Consulta de uso/saldo da conta no OpenRouter.

Usado tanto para mostrar o gasto dentro do menu quanto para alimentar a
statusline do Claude Code. Consulta ``/api/v1/credits``, que devolve o total de
créditos e o total já consumido na conta da chave informada.
"""

from __future__ import annotations

import http.client
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

CREDITS_URL = "https://openrouter.ai/api/v1/credits"

# Desfechos de ``check_api_key``. Só ``CHAVE_RECUSADA`` diz algo sobre a chave:
# rede fora, timeout ou servidor com problema nunca podem virar "chave inválida".
CHAVE_VALIDA = "valida"
CHAVE_RECUSADA = "recusada"
OPENROUTER_INDISPONIVEL = "indisponivel"


class UsageError(RuntimeError):
    """Falha ao consultar o uso no OpenRouter."""


class ChaveRecusadaError(UsageError):
    """O OpenRouter respondeu 401/403: a chave em si não serve."""


@dataclass(frozen=True)
class Usage:
    """Saldo da conta no OpenRouter (valores em US$)."""

    total_credits: float
    total_usage: float

    @property
    def remaining(self) -> float:
        return self.total_credits - self.total_usage


@dataclass(frozen=True)
class KeyCheck:
    """Resultado de validar uma chave contra o OpenRouter.

    ``status`` é um de ``CHAVE_VALIDA``, ``CHAVE_RECUSADA`` ou
    ``OPENROUTER_INDISPONIVEL``. ``saldo_zerado`` só é verdadeiro quando o
    OpenRouter devolveu o saldo e ele acabou; saldo desconhecido não avisa.
    """

    status: str
    reason: str
    saldo_zerado: bool = False

    @property
    def ok(self) -> bool:
        return self.status == CHAVE_VALIDA

    def __bool__(self) -> bool:
        return self.ok


def _credits_request(api_key: str, timeout: float) -> dict:
    """Faz a chamada a ``/credits`` e devolve o JSON; levanta ``UsageError``.

    Distingue a falha de autenticação (401/403) das demais para que o chamador
    saiba se o problema é a chave em si ou a rede.
    """
    if not api_key:
        raise UsageError("chave do OpenRouter ausente.")
    req = urllib.request.Request(
        CREDITS_URL,
        headers={"Authorization": f"Bearer {api_key}", "User-Agent": "openia"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (URL fixa, https)
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise ChaveRecusadaError(
                "a chave foi rejeitada pelo OpenRouter (inválida, revogada "
                "ou sem permissão)." + _resposta_do_openrouter(exc)
            ) from exc
        raise UsageError(f"o OpenRouter respondeu com erro HTTP {exc.code}.") from exc
    # OSError cobre URLError, timeout e conexão derrubada no meio da resposta
    # (RemoteDisconnected/ConnectionResetError, que antes escapavam daqui).
    except (OSError, http.client.HTTPException, json.JSONDecodeError) as exc:
        raise UsageError(f"não foi possível consultar o OpenRouter: {exc}") from exc


def _resposta_do_openrouter(exc: urllib.error.HTTPError) -> str:
    """Mensagem curta do corpo de erro do OpenRouter, para o motivo da recusa.

    O 403 também significa "limite da chave esgotado" (``Key limit exceeded``):
    sem a resposta do servidor, o motivo genérico mandaria trocar uma chave que
    só precisa de limite. Nada que pareça chave passa; corpo estranho é ignorado.
    """
    try:
        corpo = json.loads(exc.read().decode("utf-8", "replace"))
        mensagem = str(corpo["error"]["message"])
    except (AttributeError, KeyError, OSError, TypeError, ValueError):
        return ""
    mensagem = re.sub(r"sk-or-\S*", "[chave omitida]", " ".join(mensagem.split()))
    return f" Resposta do OpenRouter: {mensagem[:160]}" if mensagem else ""


def _saldo_zerado(payload: dict) -> bool:
    """True só quando o saldo veio na resposta e acabou."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return False
    try:
        restante = float(data["total_credits"]) - float(data["total_usage"])
    except (KeyError, TypeError, ValueError):
        return False
    return restante <= 0


def check_api_key(api_key: str, timeout: float = 10.0) -> KeyCheck:
    """Valida a chave *de verdade*, autenticando contra o OpenRouter.

    Diferente de ``config.validate_api_key`` (que só confere o formato), esta
    chama a rede: uma chave bem-formada mas revogada aqui aparece como
    recusada. Não levanta exceção — devolve um ``KeyCheck`` com o desfecho e o
    motivo, para o chamador decidir sem try/except. A chave só é usada no
    cabeçalho da requisição; nenhum motivo devolvido a contém.
    """
    if not api_key:
        return KeyCheck(CHAVE_RECUSADA, "chave do OpenRouter ausente.")
    try:
        payload = _credits_request(api_key, timeout)
    except ChaveRecusadaError as exc:
        return KeyCheck(CHAVE_RECUSADA, str(exc))
    except UsageError as exc:
        return KeyCheck(OPENROUTER_INDISPONIVEL, str(exc))
    return KeyCheck(
        CHAVE_VALIDA,
        "chave válida e autenticada no OpenRouter.",
        saldo_zerado=_saldo_zerado(payload),
    )


def fetch_usage(api_key: str, timeout: float = 10.0) -> Usage:
    """Busca uso/saldo no OpenRouter. Levanta ``UsageError`` em falha."""
    payload = _credits_request(api_key, timeout)

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
