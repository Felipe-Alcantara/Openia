"""Testes do registro de interfaces e do contrato AIInterface."""

from __future__ import annotations

import pytest

from openia.interfaces import registry
from openia.interfaces.base import AIInterface, Ecosystem


def test_todas_interfaces_tem_chave_unica():
    chaves = [i.key for i in registry.all_interfaces()]
    assert len(chaves) == len(set(chaves)), "há chaves duplicadas no registro"


def test_get_encontra_interface_existente():
    iface = registry.get("orchat")
    assert iface.name == "OrChat"


def test_get_chave_invalida_levanta_keyerror():
    with pytest.raises(KeyError):
        registry.get("nao-existe")


def test_contrato_rejeita_chave_nao_identificador():
    with pytest.raises(ValueError):
        AIInterface(
            key="chave-invalida",  # hífen não é identificador
            name="X",
            description="x",
            ecosystem=Ecosystem.PYTHON,
            package="x",
            command="x",
            homepage="https://example.com",
        )


def test_contrato_script_exige_install_script():
    with pytest.raises(ValueError):
        AIInterface(
            key="x",
            name="X",
            description="x",
            ecosystem=Ecosystem.SCRIPT,
            package="",
            command="x",
            homepage="https://example.com",
            # sem install_script
        )


def test_contrato_script_exige_url_https():
    with pytest.raises(ValueError):
        AIInterface(
            key="x",
            name="X",
            description="x",
            ecosystem=Ecosystem.SCRIPT,
            package="",
            command="x",
            homepage="https://example.com",
            install_script="ftp://exemplo/install",
        )


def test_agentes_de_codigo_registrados():
    for chave in ("cline", "opencode", "openclaw", "claudecode"):
        assert registry.get(chave).key == chave


def test_claudecode_usa_base_url_sem_v1():
    iface = registry.get("claudecode")
    assert iface.base_url == "https://openrouter.ai/api"
    assert "ANTHROPIC_API_KEY" in iface.clear_env


def test_claudecode_suporta_assinatura():
    assert registry.get("claudecode").supports_subscription is True
    # As demais não suportam (padrão).
    assert registry.get("opencode").supports_subscription is False
