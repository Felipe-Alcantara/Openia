"""Testes do comportamento crítico: chave (validação/gravação) e ambiente.

Foca no que tem risco real: rejeitar chave inválida, gravar com permissão
restrita, e injetar a chave nas variáveis certas sem vazar.
"""

from __future__ import annotations

import os
import stat

import pytest

from openia import config
from openia.interfaces.base import AIInterface, Ecosystem

VALID_KEY = "sk-or-v1-" + "a" * 40


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    """Isola o keys.json/.env num diretório temporário e limpa env vars."""
    monkeypatch.setattr(config, "_KEYS_PATH", tmp_path / "keys.json")
    monkeypatch.setattr(config, "_LEGACY_ENV_PATH", tmp_path / ".env")
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


def test_add_grava_com_permissao_restrita_no_unix():
    warning = config.add_key("pessoal", VALID_KEY)
    path = config.keys_path()
    assert path.exists()
    if os.name != "nt":
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o600, f"esperado 0600, veio {oct(mode)}"
        assert warning is None
    else:
        assert warning is not None  # Windows não protege por permissão


def test_load_retorna_chave_ativa():
    config.add_key("pessoal", VALID_KEY)
    assert config.load_api_key() == VALID_KEY
    assert config.active_key_name() == "pessoal"


def test_load_ausente_retorna_none():
    assert config.load_api_key() is None


def test_multiplas_chaves_e_troca_de_ativa():
    outra = "sk-or-v1-" + "c" * 40
    config.add_key("pessoal", VALID_KEY)
    config.add_key("trabalho", outra, make_active=False)
    assert {nk.name for nk in config.list_keys()} == {"pessoal", "trabalho"}
    assert config.load_api_key() == VALID_KEY  # pessoal continua ativa
    config.set_active("trabalho")
    assert config.load_api_key() == outra


def test_rename_preserva_ativa():
    config.add_key("pessoal", VALID_KEY)
    config.rename_key("pessoal", "principal")
    assert config.active_key_name() == "principal"
    assert config.load_api_key() == VALID_KEY


def test_remove_ativa_escolhe_outra():
    outra = "sk-or-v1-" + "d" * 40
    config.add_key("a", VALID_KEY)
    config.add_key("b", outra, make_active=False)
    config.set_active("a")
    config.remove_key("a")
    assert config.active_key_name() == "b"


def test_migra_env_antigo(tmp_path, monkeypatch):
    legacy = tmp_path / ".env"
    legacy.write_text(f"{config.ENV_VAR}={VALID_KEY}\n", encoding="utf-8")
    monkeypatch.setattr(config, "_LEGACY_ENV_PATH", legacy)
    # keys.json ainda não existe → deve migrar a chave antiga como 'padrão'.
    assert config.load_api_key() == VALID_KEY
    assert config.active_key_name() == "padrão"


def test_env_var_tem_prioridade_sobre_arquivo(monkeypatch):
    config.add_key("pessoal", VALID_KEY)
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
