"""Testes do módulo de uso/saldo do OpenRouter (sem rede)."""

from __future__ import annotations

import http.client
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


def _urlopen_que_levanta(erro):
    def _open(req, timeout=None):  # noqa: ARG001
        raise erro

    return _open


@pytest.mark.parametrize("codigo", [401, 403])
def test_check_api_key_classifica_recusa_do_openrouter(monkeypatch, codigo):
    erro = urllib.error.HTTPError("u", codigo, "Unauthorized", {}, io.BytesIO(b""))
    monkeypatch.setattr(usage.urllib.request, "urlopen", _urlopen_que_levanta(erro))

    resultado = usage.check_api_key("sk-or-revogada")

    assert resultado.status == usage.CHAVE_RECUSADA
    assert not resultado.ok


def test_check_api_key_recusa_traz_a_resposta_do_openrouter(monkeypatch):
    # 403 também é "limite da chave esgotado" (medido em 07/10): o motivo
    # genérico enganaria, então a resposta curta do OpenRouter vai junto.
    corpo = b'{"error": {"message": "Key limit exceeded", "code": 403}}'
    erro = urllib.error.HTTPError("u", 403, "Forbidden", {}, io.BytesIO(corpo))
    monkeypatch.setattr(usage.urllib.request, "urlopen", _urlopen_que_levanta(erro))

    resultado = usage.check_api_key("sk-or-com-limite")

    assert resultado.status == usage.CHAVE_RECUSADA
    assert "Key limit exceeded" in resultado.reason


def test_check_api_key_resposta_do_openrouter_nunca_ecoa_chave(monkeypatch):
    corpo = b'{"error": {"message": "bad key sk-or-v1-abc123def456 here"}}'
    erro = urllib.error.HTTPError("u", 401, "Unauthorized", {}, io.BytesIO(corpo))
    monkeypatch.setattr(usage.urllib.request, "urlopen", _urlopen_que_levanta(erro))

    resultado = usage.check_api_key("sk-or-v1-abc123def456")

    assert "abc123" not in resultado.reason
    assert "[chave omitida]" in resultado.reason


# Rede fora, servidor com problema ou resposta estranha não dizem nada sobre a
# chave: nunca podem virar "chave recusada".
@pytest.mark.parametrize(
    "erro",
    [
        urllib.error.HTTPError("u", 500, "Internal", {}, io.BytesIO(b"")),
        urllib.error.HTTPError("u", 429, "Too Many Requests", {}, io.BytesIO(b"")),
        urllib.error.URLError("sem rede"),
        TimeoutError("lento"),
        http.client.RemoteDisconnected("conexão caiu"),
        ConnectionResetError("reset"),
    ],
    ids=["http-500", "http-429", "sem-rede", "timeout", "conexao-caiu", "reset"],
)
def test_check_api_key_falha_de_rede_ou_servidor_fica_indisponivel(monkeypatch, erro):
    monkeypatch.setattr(usage.urllib.request, "urlopen", _urlopen_que_levanta(erro))

    resultado = usage.check_api_key("sk-or-qualquer")

    assert resultado.status == usage.OPENROUTER_INDISPONIVEL
    assert not resultado.ok


def test_check_api_key_json_invalido_fica_indisponivel(monkeypatch):
    def _open(req, timeout=None):  # noqa: ARG001
        class Resp:
            def read(self):
                return b"<html>manutencao</html>"

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return Resp()

    monkeypatch.setattr(usage.urllib.request, "urlopen", _open)

    assert usage.check_api_key("sk-or-qualquer").status == usage.OPENROUTER_INDISPONIVEL


def test_check_api_key_valida_com_saldo(monkeypatch):
    monkeypatch.setattr(
        usage.urllib.request, "urlopen",
        _fake_urlopen_ok({"data": {"total_credits": 5, "total_usage": 1}}),
    )

    resultado = usage.check_api_key("sk-or-valida")

    assert resultado.status == usage.CHAVE_VALIDA
    assert resultado.saldo_zerado is False


def test_check_api_key_valida_sem_saldo_avisa(monkeypatch):
    monkeypatch.setattr(
        usage.urllib.request, "urlopen",
        _fake_urlopen_ok({"data": {"total_credits": 5, "total_usage": 5}}),
    )

    resultado = usage.check_api_key("sk-or-valida")

    assert resultado.ok
    assert resultado.saldo_zerado is True


def test_check_api_key_saldo_desconhecido_nao_avisa(monkeypatch):
    monkeypatch.setattr(
        usage.urllib.request, "urlopen", _fake_urlopen_ok({"data": None})
    )

    resultado = usage.check_api_key("sk-or-valida")

    assert resultado.ok
    assert resultado.saldo_zerado is False


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
