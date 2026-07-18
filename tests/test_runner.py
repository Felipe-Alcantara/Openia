"""Testes do runner: o gate de consentimento para instaladores via script.

Não exercita instalação real (rede); valida a regra de segurança de que um
instalador SCRIPT só roda com consentimento explícito.
"""

from __future__ import annotations

import pytest

from openia import runner
from openia.interfaces.base import AIInterface, Ecosystem

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


def test_run_resolve_executavel_via_which(monkeypatch):
    # No Windows a CLI é 'claude.cmd'; run() deve invocar o caminho resolvido
    # pelo which, não o nome cru (que falharia em CreateProcess com WinError 2).
    iface = AIInterface(
        key="claude_like", name="ClaudeLike", description="x",
        ecosystem=Ecosystem.NODE, package="x", command="claude",
        homepage="https://example.com",
    )
    monkeypatch.setattr(
        runner.shutil, "which",
        lambda x: r"C:\\Users\\b\\claude.cmd" if x == "claude" else None,
    )
    capturado = {}

    def fake_run(cmd, env=None, cwd=None):
        capturado["cmd"] = cmd
        capturado["cwd"] = cwd

        class R:
            returncode = 0

        return R()

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    rc = runner.run(iface, api_key="k")
    assert rc == 0
    assert capturado["cmd"][0] == r"C:\\Users\\b\\claude.cmd"
    # Sem cwd explícito, herda o do openia (None repassado ao subprocess).
    assert capturado["cwd"] is None


def test_run_repassa_cwd_ao_subprocess(monkeypatch, tmp_path):
    # Agentes de código precisam rodar na raiz do projeto: o cwd deve chegar
    # ao subprocess, senão o agente abre na pasta errada e o histórico (Claude
    # Code, indexado por caminho) não bate com o do editor.
    iface = AIInterface(
        key="agente", name="Agente", description="x",
        ecosystem=Ecosystem.NODE, package="x", command="claude",
        homepage="https://example.com", is_code_agent=True,
    )
    monkeypatch.setattr(runner.shutil, "which", lambda x: "/bin/claude")
    capturado = {}

    def fake_run(cmd, env=None, cwd=None):
        capturado["cwd"] = cwd

        class R:
            returncode = 0

        return R()

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    rc = runner.run(iface, api_key="k", cwd=str(tmp_path))
    assert rc == 0
    assert capturado["cwd"] == str(tmp_path)


def test_run_sem_executavel_no_path_falha(monkeypatch):
    iface = AIInterface(
        key="claude_like", name="ClaudeLike", description="x",
        ecosystem=Ecosystem.NODE, package="x", command="claude",
        homepage="https://example.com",
    )
    monkeypatch.setattr(runner.shutil, "which", lambda x: None)
    with pytest.raises(runner.ToolingError) as exc:
        runner.run(iface, api_key="k")
    assert "não está instalada" in str(exc.value)


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


def test_open_in_new_terminal_sem_emulador_devolve_false(monkeypatch):
    """Sem emulador no PATH (ex.: SSH puro), devolve False para o chamador decidir."""
    monkeypatch.setattr(runner.os, "name", "posix")
    monkeypatch.setattr(runner.sys, "platform", "linux")
    monkeypatch.setattr(runner.shutil, "which", lambda x: None)
    assert runner.open_in_new_terminal(["echo", "oi"]) is False


def test_open_in_new_terminal_usa_emulador_disponivel(monkeypatch):
    """Acha o primeiro emulador do PATH e lança o comando nele, sem bloquear."""
    monkeypatch.setattr(runner.os, "name", "posix")
    monkeypatch.setattr(runner.sys, "platform", "linux")
    monkeypatch.setattr(
        runner.shutil, "which",
        lambda x: "/usr/bin/konsole" if x == "konsole" else None,
    )
    chamadas = []
    monkeypatch.setattr(runner.subprocess, "Popen", lambda cmd, **kw: chamadas.append(cmd))
    assert runner.open_in_new_terminal(["prog", "--flag"]) is True
    assert chamadas == [["/usr/bin/konsole", "-e", "prog", "--flag"]]
