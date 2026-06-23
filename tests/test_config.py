"""Testes do comportamento crítico: chave (validação/gravação) e ambiente.

Foca no que tem risco real: rejeitar chave inválida, gravar com permissão
restrita, e injetar a chave nas variáveis certas sem vazar.
"""

from __future__ import annotations

import os
import stat

import pytest

from orctl import config
from orctl.interfaces.base import AIInterface, Ecosystem

VALID_KEY = "sk-or-v1-" + "a" * 40


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    """Aponta o .env para um diretório temporário e limpa env vars relevantes."""
    monkeypatch.setattr(config, "_ENV_PATH", tmp_path / ".env")
    monkeypatch.delenv(config.ENV_VAR, raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)


def test_validate_rejeita_vazia():
    with pytest.raises(ValueError):
        config.validate_api_key("   ")


def test_validate_rejeita_formato_errado():
    with pytest.raises(ValueError):
        config.validate_api_key("chave-qualquer-1234567890")


def test_validate_aceita_chave_openrouter():
    assert config.validate_api_key(f"  {VALID_KEY}  ") == VALID_KEY


def test_save_grava_com_permissao_restrita_no_unix():
    path, warning = config.save_api_key(VALID_KEY)
    assert path.exists()
    assert VALID_KEY in path.read_text(encoding="utf-8")
    if os.name != "nt":
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o600, f"esperado 0600, veio {oct(mode)}"
        assert warning is None
    else:
        assert warning is not None  # Windows não protege por permissão


def test_load_le_do_arquivo():
    config.save_api_key(VALID_KEY)
    assert config.load_api_key() == VALID_KEY


def test_load_ausente_retorna_none():
    assert config.load_api_key() is None


def test_env_var_tem_prioridade_sobre_arquivo(monkeypatch):
    config.save_api_key(VALID_KEY)
    outra = "sk-or-v1-" + "b" * 40
    monkeypatch.setenv(config.ENV_VAR, outra)
    assert config.load_api_key() == outra


def test_build_run_env_injeta_chave_e_aliases():
    iface = AIInterface(
        key="exemplo",
        name="Exemplo",
        description="teste",
        ecosystem=Ecosystem.PYTHON,
        package="exemplo",
        command="exemplo",
        homepage="https://example.com",
        env_keys=("OPENAI_API_KEY",),
        base_url_env="OPENAI_API_BASE",
    )
    env = config.build_run_env(iface, VALID_KEY)
    assert env[config.ENV_VAR] == VALID_KEY
    assert env["OPENAI_API_KEY"] == VALID_KEY
    assert env["OPENAI_API_BASE"].startswith("https://openrouter.ai")


def test_build_run_env_base_url_custom_e_clear_env(monkeypatch):
    # Simula uma chave Anthropic já no ambiente que precisa ser esvaziada.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "valor-antigo")
    iface = AIInterface(
        key="claude_like",
        name="ClaudeLike",
        description="teste",
        ecosystem=Ecosystem.NODE,
        package="x",
        command="x",
        homepage="https://example.com",
        env_keys=("ANTHROPIC_AUTH_TOKEN",),
        base_url_env="ANTHROPIC_BASE_URL",
        base_url="https://openrouter.ai/api",
        clear_env=("ANTHROPIC_API_KEY",),
    )
    env = config.build_run_env(iface, VALID_KEY)
    assert env["ANTHROPIC_AUTH_TOKEN"] == VALID_KEY
    assert env["ANTHROPIC_BASE_URL"] == "https://openrouter.ai/api"  # sem /v1
    assert env["ANTHROPIC_API_KEY"] == ""  # esvaziada
