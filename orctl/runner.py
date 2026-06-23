"""Instalação, detecção e execução das interfaces de IA.

Esta camada isola as chamadas a ``pip``, ``npm`` e ao sistema operacional.
Decisão de instalação (escolhida pelo usuário): instalar direto no sistema
(pip/npm global), sem isolamento por venv/pipx.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

from .config import build_run_env
from .interfaces.base import AIInterface, Ecosystem


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
        # Usa o mesmo interpretador que roda o orctl, evitando ambiguidade de pip.
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade", interface.package]
    elif interface.ecosystem is Ecosystem.NODE:
        _require("npm", "Instale o Node.js (que traz o npm) e tente de novo.")
        cmd = ["npm", "install", "--global", interface.package]
    elif interface.ecosystem is Ecosystem.SCRIPT:
        if not allow_script:
            raise ToolingError(
                f"{interface.name} instala executando um script remoto "
                f"({interface.install_script}). Confirme antes de prosseguir."
            )
        _require("curl", "Instale o curl e tente de novo.")
        _require("bash", "Instale o bash e tente de novo.")
        # curl -fsSL <url> | bash — instalador oficial da ferramenta.
        cmd = ["bash", "-c", f"curl -fsSL {interface.install_script} | bash"]
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


def run(
    interface: AIInterface,
    api_key: str,
    extra_args: list[str] | None = None,
    model_id: str | None = None,
) -> int:
    """Executa a interface, repassando a chave via ambiente. Retorna o exit code.

    A chave vai pelo ambiente do processo filho (não por argumento), para não
    vazar em listagem de processos nem em histórico de shell.

    Se ``model_id`` for dado e a ferramenta aceitar modelo por flag/env, ele é
    aplicado no formato esperado por ela (ver ``AIInterface.model_ref``). Para
    ferramentas que só escolhem o modelo na própria UI, ``model_id`` é ignorado
    aqui (o CLI cuida de instruir o usuário).
    """
    if not is_installed(interface):
        raise ToolingError(
            f"{interface.name} não está instalada. Rode a instalação primeiro."
        )

    env = build_run_env(interface, api_key)
    model_args: list[str] = []
    if model_id and interface.supports_model_selection():
        ref = interface.model_ref(model_id)
        if interface.model_env:
            env[interface.model_env] = ref
        if interface.model_arg:
            model_args = [interface.model_arg, ref]

    cmd = [interface.command, *interface.run_args, *model_args, *(extra_args or [])]
    # Sem capturar saída: a CLI é interativa e assume o terminal do usuário.
    completed = subprocess.run(cmd, env=env)
    return completed.returncode
