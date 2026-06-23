"""Testes do catálogo de modelos: parsing, agrupamento, cache e model_ref.

Não acessa a rede: injeta payload/cache para validar a lógica de forma estável.
"""

from __future__ import annotations

import json

import pytest

from orctl import models
from orctl.interfaces.base import AIInterface, Ecosystem

PAYLOAD = {
    "data": [
        {"id": "anthropic/claude-opus-4.1", "name": "Claude Opus 4.1",
         "pricing": {"completion": "0.000075"}},
        {"id": "anthropic/claude-sonnet-4", "name": "Claude Sonnet 4",
         "pricing": {"completion": "0.000015"}},
        {"id": "google/gemini-2.5-pro", "name": "Gemini 2.5 Pro",
         "pricing": {"completion": "0.00001"}},
        {"id": "sem-barra", "name": "ignorar"},  # malformado: sem vendor
        {"name": "sem id"},  # sem id
    ]
}


def test_parse_ignora_malformados():
    parsed = models._parse_models(PAYLOAD)
    ids = {m.id for m in parsed}
    assert ids == {
        "anthropic/claude-opus-4.1",
        "anthropic/claude-sonnet-4",
        "google/gemini-2.5-pro",
    }


def test_vendors_ordenados_e_unicos():
    parsed = models._parse_models(PAYLOAD)
    assert models.vendors(parsed) == ["anthropic", "google"]


def test_models_of_ordena_por_preco_desc():
    parsed = models._parse_models(PAYLOAD)
    anthropic = models.models_of(parsed, "anthropic")
    nomes = [m.name for m in anthropic]
    # Opus (0.000075) é mais caro que Sonnet (0.000015), então vem primeiro.
    assert nomes == ["Claude Opus 4.1", "Claude Sonnet 4"]
    assert anthropic[0].completion_price > anthropic[1].completion_price


def test_modelo_sem_pricing_vai_para_o_fim():
    payload = {
        "data": [
            {"id": "x/barato", "name": "Barato", "pricing": {"completion": "0.001"}},
            {"id": "x/sem-preco", "name": "SemPreco"},  # sem pricing → 0.0
        ]
    }
    ordenados = models.models_of(models._parse_models(payload), "x")
    assert [m.name for m in ordenados] == ["Barato", "SemPreco"]


def test_load_models_usa_cache_quando_rede_falha(tmp_path, monkeypatch):
    cache = tmp_path / ".models_cache.json"
    parsed = models._parse_models(PAYLOAD)
    cache.write_text(
        json.dumps({"models": [m.__dict__ for m in parsed]}), encoding="utf-8"
    )
    monkeypatch.setattr(models, "_CACHE_PATH", cache)

    def boom(timeout):
        raise models.CatalogError("rede caiu")

    monkeypatch.setattr(models, "_fetch_remote", boom)

    # force_refresh para pular o atalho de cache fresco e exercitar o fallback.
    resultado = models.load_models(force_refresh=True)
    assert len(resultado) == 3


def test_load_models_sem_rede_e_sem_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "_CACHE_PATH", tmp_path / "inexistente.json")

    def boom(timeout):
        raise models.CatalogError("rede caiu")

    monkeypatch.setattr(models, "_fetch_remote", boom)
    with pytest.raises(models.CatalogError):
        models.load_models(force_refresh=True)


def test_model_ref_aplica_prefixo():
    com_prefixo = AIInterface(
        key="x", name="X", description="x", ecosystem=Ecosystem.NODE,
        package="x", command="x", homepage="https://example.com",
        model_prefix="openrouter/",
    )
    assert com_prefixo.model_ref("anthropic/claude") == "openrouter/anthropic/claude"

    sem_prefixo = AIInterface(
        key="y", name="Y", description="y", ecosystem=Ecosystem.NODE,
        package="y", command="y", homepage="https://example.com",
        model_arg="-m",
    )
    assert sem_prefixo.model_ref("anthropic/claude") == "anthropic/claude"
    assert sem_prefixo.supports_model_selection() is True
    assert com_prefixo.supports_model_selection() is False
