"""Testes da lógica de navegação do menu (sem terminal interativo real)."""

from __future__ import annotations

import pytest

from openia import cli
from openia.interfaces import registry


def test_decide_mode_voltar_cancela(monkeypatch):
    """Escolher voltar (0) em 'como autenticar' deve cancelar, não avançar."""
    # _pick_from devolve None quando o usuário escolhe voltar.
    monkeypatch.setattr(cli, "_pick_from", lambda *a, **k: None)
    iface = registry.get("claudecode")  # suporta assinatura → faz a pergunta
    with pytest.raises(cli._Cancelado):
        cli._decide_mode(iface, subscription=False, provider=False)


def test_decide_mode_openrouter_e_assinatura(monkeypatch):
    iface = registry.get("claudecode")
    # idx 0 = OpenRouter (provider=True)
    monkeypatch.setattr(cli, "_pick_from", lambda *a, **k: 0)
    assert cli._decide_mode(iface, False, False) is True
    # idx 1 = assinatura (provider=False)
    monkeypatch.setattr(cli, "_pick_from", lambda *a, **k: 1)
    assert cli._decide_mode(iface, False, False) is False


def test_decide_mode_sem_assinatura_sempre_provider():
    """Interface que não suporta assinatura nunca pergunta: é sempre provider."""
    iface = registry.get("opencode")
    assert cli._decide_mode(iface, False, False) is True


def test_pick_from_zero_devolve_none(monkeypatch):
    """Escolher 0 (voltar) devolve None, nunca um índice."""
    monkeypatch.setattr(cli.ui, "ask_number", lambda *a, **k: 0)
    assert cli._pick_from("t", ["a", "b"]) is None


def test_pick_from_repete_ate_opcao_valida(monkeypatch):
    """Opção fora do intervalo repete o menu (em loop) até uma escolha válida."""
    respostas = iter([99, -1, 2])
    monkeypatch.setattr(cli.ui, "ask_number", lambda *a, **k: next(respostas))
    assert cli._pick_from("t", ["a", "b"]) == 1
