"""Instalação, detecção e execução das interfaces de IA.

Esta camada isola as chamadas a ``pip``, ``npm`` e ao sistema operacional.
Decisão de instalação (escolhida pelo usuário): instalar direto no sistema
(pip/npm global), sem isolamento por venv/pipx.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from .config import build_run_env
from .interfaces.base import AIInterface, Ecosystem

# No Windows o executável do npm é npm.cmd; nos demais SOs é npm.
NPM = "npm.cmd" if os.name == "nt" else "npm"


class ToolingError(RuntimeError):
    """Erro previsível ao instalar ou executar uma interface."""


def _require(executable: str, dica: str) -> str:
    """Garante que um executável existe no PATH ou levanta erro claro."""
    found = shutil.which(executable)
    if not found:
        raise ToolingError(
            f"'{executable}' não encontrado no PATH. {dica}"
        )
    return found


def is_installed(interface: AIInterface) -> bool:
    """Diz se a CLI da interface já está disponível no PATH."""
    return shutil.which(interface.command) is not None


def install(interface: AIInterface, allow_script: bool = False) -> None:
    """Instala a interface direto no sistema (pip/npm global, ou script oficial).

    ``allow_script`` precisa ser ``True`` para instalar ferramentas do
    ecossistema SCRIPT, que baixam e executam um instalador remoto via shell —
    o chamador deve obter consentimento explícito do usuário antes.

    Levanta ``ToolingError`` com a saída do instalador quando ele falha, para o
    chamador exibir algo acionável.
    """
    if interface.ecosystem is Ecosystem.PYTHON:
        # Usa o mesmo interpretador que roda o openia, evitando ambiguidade de pip.
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade", interface.package]
    elif interface.ecosystem is Ecosystem.NODE:
        _require(NPM, "Instale o Node.js (que traz o npm) e tente de novo.")
        cmd = [NPM, "install", "--global", interface.package]
    elif interface.ecosystem is Ecosystem.SCRIPT:
        if not allow_script:
            raise ToolingError(
                f"{interface.name} instala executando um script remoto "
                f"({interface.install_script}). Confirme antes de prosseguir."
            )
        cmd = _script_install_cmd(interface)
    else:  # pragma: no cover - enum fechado
        raise ToolingError(f"ecossistema não suportado: {interface.ecosystem}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        alvo = interface.install_script or f"pacote '{interface.package}'"
        raise ToolingError(
            f"falha ao instalar {interface.name} ({alvo}).\n"
            f"Comando: {' '.join(cmd)}\n"
            f"{result.stderr.strip() or result.stdout.strip()}"
        )


def _script_install_cmd(interface: AIInterface) -> list[str]:
    """Monta o comando do instalador oficial conforme o SO.

    Unix usa ``curl … | sh``; Windows usa PowerShell com ``irm | iex``. Se o
    pré-requisito não existir, levanta ``ToolingError`` com instrução clara.
    """
    url = interface.install_script
    if os.name == "nt":
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if not powershell:
            raise ToolingError(
                f"PowerShell não encontrado para instalar {interface.name}. "
                f"Instale manualmente seguindo {interface.homepage}."
            )
        return [powershell, "-NoProfile", "-Command", f"irm {url} | iex"]
    _require("curl", "Instale o curl e tente de novo.")
    # 'sh' existe em qualquer Unix; não exige bash especificamente.
    return ["sh", "-c", f"curl -fsSL {url} | sh"]


def run(
    interface: AIInterface,
    api_key: str | None,
    extra_args: list[str] | None = None,
    model_id: str | None = None,
    use_provider: bool = True,
) -> int:
    """Executa a interface. Retorna o exit code.

    Com ``use_provider=True`` (padrão), injeta a chave/base_url do OpenRouter via
    ambiente do processo filho — sem passar por argumento, para não vazar em
    listagem de processos nem em histórico de shell.

    Com ``use_provider=False`` (modo assinatura), roda a ferramenta com o
    ambiente do sistema mas **remove** as variáveis do provider que ela usaria,
    para não sobrescrever a autenticação própria da ferramenta (ex.: o login de
    assinatura do Claude Code, que exige ausência de ``ANTHROPIC_*``).

    Se ``model_id`` for dado e a ferramenta aceitar modelo por flag/env, ele é
    aplicado no formato esperado por ela (ver ``AIInterface.model_ref``).
    """
    # Resolve o caminho real do executável. No Windows a CLI costuma ser um
    # 'claude.cmd'/'.bat'; o CreateProcess (shell=False) não aplica PATHEXT nem
    # procura no PATH, então passar só 'claude' falha com WinError 2. O which()
    # resolve a extensão correta em qualquer SO e ainda confirma a instalação.
    executable = shutil.which(interface.command)
    if not executable:
        raise ToolingError(
            f"{interface.name} não está instalada. Rode a instalação primeiro."
        )

    if use_provider:
        if not api_key:
            raise ToolingError("chave do OpenRouter ausente para o modo provider.")
        env = build_run_env(interface, api_key)
    else:
        env = _env_without_provider(interface)

    model_args: list[str] = []
    if model_id and interface.supports_model_selection():
        ref = interface.model_ref(model_id)
        if interface.model_env:
            env[interface.model_env] = ref
        if interface.model_arg:
            model_args = [interface.model_arg, ref]

    cmd = [executable, *interface.run_args, *model_args, *(extra_args or [])]
    # Sem capturar saída: a CLI é interativa e assume o terminal do usuário.
    completed = subprocess.run(cmd, env=env)
    return completed.returncode


def _env_without_provider(interface: AIInterface) -> dict[str, str]:
    """Ambiente do sistema sem as variáveis que apontariam para o OpenRouter.

    Remove a base_url, os apelidos de chave e as variáveis de ``clear_env`` desta
    interface, para que a ferramenta use sua própria autenticação (assinatura).
    """
    import os

    env = dict(os.environ)
    para_remover = set(interface.env_keys) | set(interface.clear_env)
    if interface.base_url_env:
        para_remover.add(interface.base_url_env)
    for name in para_remover:
        env.pop(name, None)
    return env
