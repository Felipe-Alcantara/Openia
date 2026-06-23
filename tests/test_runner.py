"""Testes do runner: o gate de consentimento para instaladores via script.

Não exercita instalação real (rede); valida a regra de segurança de que um
instalador SCRIPT só roda com consentimento explícito.
"""

from __future__ import annotations

import pytest

from orctl import runner
from orctl.interfaces.base import AIInterface, Ecosystem

SCRIPT_IFACE = AIInterface(
    key="exemplo_script",
    name="ExemploScript",
    description="teste",
    ecosystem=Ecosystem.SCRIPT,
    package="",
    command="exemplo_script",
    homepage="https://example.com",
    install_script="https://example.com/install",
)


def test_install_script_sem_consentimento_falha():
    with pytest.raises(runner.ToolingError) as exc:
        runner.install(SCRIPT_IFACE, allow_script=False)
    assert "script remoto" in str(exc.value)


def test_script_install_unix_usa_curl_sh(monkeypatch):
    monkeypatch.setattr(runner.os, "name", "posix")
    monkeypatch.setattr(runner.shutil, "which", lambda x: f"/usr/bin/{x}")
    cmd = runner._script_install_cmd(SCRIPT_IFACE)
    assert cmd[0] == "sh"
    assert "curl -fsSL" in cmd[-1] and cmd[-1].endswith("| sh")


def test_script_install_windows_usa_powershell(monkeypatch):
    monkeypatch.setattr(runner.os, "name", "nt")
    monkeypatch.setattr(
        runner.shutil, "which",
        lambda x: "powershell.exe" if "powershell" in x else None,
    )
    cmd = runner._script_install_cmd(SCRIPT_IFACE)
    assert "powershell" in cmd[0].lower()
    assert "iex" in cmd[-1]


def test_script_install_windows_sem_powershell_falha(monkeypatch):
    monkeypatch.setattr(runner.os, "name", "nt")
    monkeypatch.setattr(runner.shutil, "which", lambda x: None)
    with pytest.raises(runner.ToolingError):
        runner._script_install_cmd(SCRIPT_IFACE)


def test_env_sem_provider_remove_variaveis(monkeypatch):
    # Simula variáveis do OpenRouter já no ambiente, que o modo assinatura limpa.
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://openrouter.ai/api")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "antiga")
    iface = AIInterface(
        key="claude_like", name="ClaudeLike", description="x",
        ecosystem=Ecosystem.NODE, package="x", command="x",
        homepage="https://example.com",
        env_keys=("ANTHROPIC_AUTH_TOKEN",),
        base_url_env="ANTHROPIC_BASE_URL",
        clear_env=("ANTHROPIC_API_KEY",),
        supports_subscription=True,
    )
    env = runner._env_without_provider(iface)
    assert "ANTHROPIC_AUTH_TOKEN" not in env
    assert "ANTHROPIC_BASE_URL" not in env
    assert "ANTHROPIC_API_KEY" not in env
