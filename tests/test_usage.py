"""Testes do módulo de uso/saldo do OpenRouter (sem rede)."""

from __future__ import annotations

import pytest

from orctl import usage


def test_remaining_calcula_saldo():
    u = usage.Usage(total_credits=10.0, total_usage=2.5)
    assert u.remaining == 7.5


def test_format_line_mostra_uso_e_saldo():
    u = usage.Usage(total_credits=10.0, total_usage=0.0175)
    linha = usage.format_line(u)
    assert "0.0175" in linha
    assert "9.98" in linha  # resta ~9.98


def test_fetch_sem_chave_falha():
    with pytest.raises(usage.UsageError):
        usage.fetch_usage("")
