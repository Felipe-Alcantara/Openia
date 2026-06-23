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


def install(interface: AIInterface) -> None:
    """Instala a interface direto no sistema (pip/npm global).

    Levanta ``ToolingError`` com a saída do gerenciador quando a instalação
    falha, para o chamador exibir algo acionável.
    """
    if interface.ecosystem is Ecosystem.PYTHON:
        # Usa o mesmo interpretador que roda o orctl, evitando ambiguidade de pip.
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade", interface.package]
    elif interface.ecosystem is Ecosystem.NODE:
        _require("npm", "Instale o Node.js (que traz o npm) e tente de novo.")
        cmd = ["npm", "install", "--global", interface.package]
    else:  # pragma: no cover - enum fechado
        raise ToolingError(f"ecossistema não suportado: {interface.ecosystem}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise ToolingError(
            f"falha ao instalar {interface.name} (pacote '{interface.package}').\n"
            f"Comando: {' '.join(cmd)}\n"
            f"{result.stderr.strip() or result.stdout.strip()}"
        )


def run(interface: AIInterface, api_key: str, extra_args: list[str] | None = None) -> int:
    """Executa a interface, repassando a chave via ambiente. Retorna o exit code.

    A chave vai pelo ambiente do processo filho (não por argumento), para não
    vazar em listagem de processos nem em histórico de shell.
    """
    if not is_installed(interface):
        raise ToolingError(
            f"{interface.name} não está instalada. Rode a instalação primeiro."
        )

    env = build_run_env(interface, api_key)
    cmd = [interface.command, *interface.run_args, *(extra_args or [])]
    # Sem capturar saída: a CLI é interativa e assume o terminal do usuário.
    completed = subprocess.run(cmd, env=env)
    return completed.returncode
