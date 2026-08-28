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

PYTHON_IFACE = AIInterface(
    key="exemplo_python",
    name="ExemploPython",
    description="teste",
    ecosystem=Ecosystem.PYTHON,
    package="exemplo-python",
    command="exemplo_python",
    homepage="https://example.com",
)


def test_install_script_sem_consentimento_falha():
    with pytest.raises(runner.ToolingError) as exc:
        runner.install(SCRIPT_IFACE, allow_script=False)
    assert "script remoto" in str(exc.value)


class _FakeCompletedProcess:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_install_python_repete_com_break_system_packages_quando_pep668(monkeypatch):
    chamadas = []

    def fake_run(cmd, capture_output=True, text=True):
        chamadas.append(cmd)
        if len(chamadas) == 1:
            return _FakeCompletedProcess(
                1, stderr="error: externally-managed-environment\n..."
            )
        return _FakeCompletedProcess(0, stdout="Successfully installed exemplo-python")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    runner.install(PYTHON_IFACE)  # não deve levantar

    assert len(chamadas) == 2
    assert "--break-system-packages" not in chamadas[0]
    assert chamadas[1][-1] == "--break-system-packages"


def test_install_python_nao_repete_quando_falha_por_outro_motivo(monkeypatch):
    chamadas = []

    def fake_run(cmd, capture_output=True, text=True):
        chamadas.append(cmd)
        return _FakeCompletedProcess(1, stderr="ConnectionError: could not resolve host")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    with pytest.raises(runner.ToolingError) as exc:
        runner.install(PYTHON_IFACE)

    assert len(chamadas) == 1
    assert "ConnectionError" in str(exc.value)
    assert "PEP 668" not in str(exc.value)


def test_install_python_mensagem_clara_quando_pep668_persiste(monkeypatch):
    def fake_run(cmd, capture_output=True, text=True):
        return _FakeCompletedProcess(1, stderr="error: externally-managed-environment")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    with pytest.raises(runner.ToolingError) as exc:
        runner.install(PYTHON_IFACE)

    assert "--break-system-packages" in str(exc.value)
    assert "PEP 668" in str(exc.value)


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


def test_run_aplica_modelo_por_comando_preparatorio_e_depois_abre_interface(monkeypatch):
    iface = AIInterface(
        key="configuravel", name="Configuravel", description="x",
        ecosystem=Ecosystem.NODE, package="x", command="configuravel",
        homepage="https://example.com",
        model_prefix="openrouter/",
        model_setup_args=("models", "set", "{model}"),
    )
    monkeypatch.setattr(runner.shutil, "which", lambda x: "/usr/bin/configuravel")
    chamadas = []

    def fake_run(cmd, env=None, cwd=None):
        chamadas.append((cmd, env, cwd))

        class R:
            returncode = 0

        return R()

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    assert runner.run(
        iface,
        api_key="chave-de-teste",
        model_id="anthropic/claude-sonnet-4",
        cwd="/tmp/projeto",
    ) == 0
    assert [cmd for cmd, _, _ in chamadas] == [
        ["/usr/bin/configuravel", "models", "set", "openrouter/anthropic/claude-sonnet-4"],
        ["/usr/bin/configuravel"],
    ]
    assert chamadas[0][1]["OPENROUTER_API_KEY"] == "chave-de-teste"
    assert all(cwd == "/tmp/projeto" for _, _, cwd in chamadas)


def test_run_interrompe_se_comando_preparatorio_do_modelo_falhar(monkeypatch):
    iface = AIInterface(
        key="configuravel", name="Configuravel", description="x",
        ecosystem=Ecosystem.NODE, package="x", command="configuravel",
        homepage="https://example.com", model_setup_args=("models", "set", "{model}"),
    )
    monkeypatch.setattr(runner.shutil, "which", lambda x: "/usr/bin/configuravel")
    chamadas = []

    def fake_run(cmd, env=None, cwd=None):
        chamadas.append(cmd)

        class R:
            returncode = 1

        return R()

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    with pytest.raises(runner.ToolingError, match="configurar o modelo"):
        runner.run(iface, api_key="chave-de-teste", model_id="x/model")
    assert len(chamadas) == 1


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
