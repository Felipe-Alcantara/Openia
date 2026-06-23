"""Catálogo de modelos do OpenRouter: busca, cache e agrupamento por empresa.

A escolha do usuário é feita em dois níveis — empresa → modelo —, que é como o
OpenRouter organiza os ids (``empresa/modelo``). A "versão" faz parte do nome do
modelo (ex.: ``claude-opus-4.1``), então aparece já no segundo nível.

A lista vem da API pública ``/api/v1/models`` (não exige chave para listar) e é
guardada em cache local para não consultar a rede a cada execução.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

MODELS_URL = "https://openrouter.ai/api/v1/models"
_CACHE_PATH = Path(__file__).resolve().parent / ".models_cache.json"
# Quanto tempo o cache é considerado fresco (24h). Depois disso, tenta atualizar.
_CACHE_TTL_SECONDS = 24 * 60 * 60


class CatalogError(RuntimeError):
    """Falha ao obter o catálogo de modelos (rede e cache indisponíveis)."""


@dataclass(frozen=True)
class Model:
    """Um modelo do OpenRouter.

    ``id`` é o identificador completo (``empresa/modelo``) usado pelas CLIs.
    ``vendor`` é a parte antes da barra; ``name`` é o rótulo legível.
    ``completion_price`` é o preço por token de saída (USD), usado para ordenar
    do mais caro (tende a ser o mais capaz) para o mais barato.
    """

    id: str
    vendor: str
    name: str
    completion_price: float = 0.0


def _completion_price(item: dict) -> float:
    """Extrai o preço de saída do modelo; 0.0 quando ausente ou inválido."""
    try:
        return float((item.get("pricing") or {}).get("completion", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _parse_models(payload: dict) -> list[Model]:
    """Extrai modelos do JSON da API, ignorando entradas malformadas."""
    models: list[Model] = []
    for item in payload.get("data", []):
        model_id = (item or {}).get("id", "")
        if not model_id or "/" not in model_id:
            continue
        vendor = model_id.split("/", 1)[0]
        name = (item.get("name") or model_id).strip()
        models.append(
            Model(
                id=model_id,
                vendor=vendor,
                name=name,
                completion_price=_completion_price(item),
            )
        )
    return models


def _read_cache() -> list[Model] | None:
    if not _CACHE_PATH.exists():
        return None
    try:
        raw = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        return [Model(**m) for m in raw["models"]]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def _cache_age_seconds() -> float | None:
    if not _CACHE_PATH.exists():
        return None
    return time.time() - _CACHE_PATH.stat().st_mtime


def _write_cache(models: list[Model]) -> None:
    data = {"models": [m.__dict__ for m in models]}
    try:
        _CACHE_PATH.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        # Cache é otimização; falha ao gravar não deve quebrar o fluxo.
        pass


def _fetch_remote(timeout: float) -> list[Model]:
    req = urllib.request.Request(MODELS_URL, headers={"User-Agent": "openia"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (URL fixa, https)
        payload = json.loads(resp.read().decode("utf-8"))
    models = _parse_models(payload)
    if not models:
        raise CatalogError("a API do OpenRouter não retornou modelos.")
    return models


def load_models(force_refresh: bool = False, timeout: float = 10.0) -> list[Model]:
    """Retorna o catálogo de modelos.

    Usa o cache local quando fresco; senão tenta a rede e atualiza o cache. Se a
    rede falhar mas houver cache (mesmo vencido), usa o cache e segue. Só levanta
    ``CatalogError`` quando não há nem rede nem cache.
    """
    age = _cache_age_seconds()
    cache_fresh = age is not None and age < _CACHE_TTL_SECONDS

    if not force_refresh and cache_fresh:
        cached = _read_cache()
        if cached:
            return cached

    try:
        models = _fetch_remote(timeout=timeout)
        _write_cache(models)
        return models
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, CatalogError) as exc:
        cached = _read_cache()
        if cached:
            return cached
        raise CatalogError(
            "não foi possível obter a lista de modelos do OpenRouter "
            f"(sem rede e sem cache): {exc}"
        ) from exc


def vendors(models: list[Model]) -> list[str]:
    """Empresas distintas, em ordem alfabética."""
    return sorted({m.vendor for m in models})


def models_of(models: list[Model], vendor: str) -> list[Model]:
    """Modelos de uma empresa, do mais caro (saída) para o mais barato.

    Preço alto costuma indicar modelo mais capaz, então premium fica no topo.
    O nome desempata para manter a ordem estável entre modelos de mesmo preço.
    """
    return sorted(
        (m for m in models if m.vendor == vendor),
        key=lambda m: (-m.completion_price, m.name),
    )
