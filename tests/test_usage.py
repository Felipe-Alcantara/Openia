"""Testes do módulo de uso/saldo do OpenRouter (sem rede)."""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from openia import usage


def _fake_urlopen_ok(payload):
    """Devolve um urlopen falso que responde 200 com ``payload`` em JSON."""
    def _open(req, timeout=None):  # noqa: ARG001
        class Resp:
            def read(self):
                return json.dumps(payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return Resp()

    return _open


def test_check_api_key_valida(monkeypatch):
    monkeypatch.setattr(
        usage.urllib.request, "urlopen",
        _fake_urlopen_ok({"data": {"total_credits": 5, "total_usage": 1}}),
    )
    resultado = usage.check_api_key("sk-or-valida")
    assert resultado.ok
    assert bool(resultado) is True


def test_check_api_key_rejeitada_em_401(monkeypatch):
    def _open(req, timeout=None):  # noqa: ARG001
        raise urllib.error.HTTPError("u", 401, "Unauthorized", {}, io.BytesIO(b""))

    monkeypatch.setattr(usage.urllib.request, "urlopen", _open)
    resultado = usage.check_api_key("sk-or-revogada")
    assert not resultado.ok
    assert "rejeitada" in resultado.reason


def test_check_api_key_erro_de_rede(monkeypatch):
    def _open(req, timeout=None):  # noqa: ARG001
        raise urllib.error.URLError("sem rede")

    monkeypatch.setattr(usage.urllib.request, "urlopen", _open)
    resultado = usage.check_api_key("sk-or-qualquer")
    assert not resultado.ok
    assert "OpenRouter" in resultado.reason


def test_check_api_key_sem_chave():
    resultado = usage.check_api_key("")
    assert not resultado.ok


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
