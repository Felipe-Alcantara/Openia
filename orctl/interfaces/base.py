"""Contrato de uma interface de IA de terminal que fala com o OpenRouter.

Cada CLI suportada é descrita de forma declarativa por uma instância de
``AIInterface``. O núcleo (instalador, detector, launcher) não conhece nenhuma
CLI específica: ele só sabe operar sobre este contrato. Adicionar uma nova
ferramenta é registrar mais uma ``AIInterface`` em ``interfaces/registry.py`` —
o núcleo permanece fechado para modificação (Open/Closed).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Ecosystem(str, Enum):
    """De onde a ferramenta é instalada/executada."""

    PYTHON = "python"
    NODE = "node"


@dataclass(frozen=True)
class AIInterface:
    """Descrição declarativa de uma CLI de IA compatível com OpenRouter.

    Atributos:
        key: Identificador curto e estável usado em comandos (ex.: ``orchat``).
        name: Nome legível exibido ao usuário.
        description: Uma linha explicando para que serve.
        ecosystem: Se é instalada via pip (Python) ou npm (Node).
        package: Nome do pacote no PyPI/npm a instalar.
        command: Executável que passa a existir após a instalação.
        env_keys: Variáveis de ambiente que entregam a chave/base_url do
            OpenRouter à ferramenta. ``OPENROUTER_API_KEY`` é tratada por todas;
            aqui ficam apelidos extras que a ferramenta espera
            (ex.: ``OPENAI_API_KEY`` para CLIs compatíveis com OpenAI).
        base_url_env: Variável que aponta a base_url para o OpenRouter, quando
            a ferramenta usa o protocolo compatível com OpenAI.
        homepage: Link de referência para o usuário.
        run_args: Argumentos padrão ao iniciar a ferramenta (normalmente vazio).
    """

    key: str
    name: str
    description: str
    ecosystem: Ecosystem
    package: str
    command: str
    homepage: str
    env_keys: tuple[str, ...] = field(default_factory=tuple)
    base_url_env: str | None = None
    run_args: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.key or not self.key.isidentifier():
            raise ValueError(
                f"key inválida para interface: {self.key!r} "
                "(use um identificador simples, ex.: 'orchat')"
            )
        if not self.package:
            raise ValueError(f"interface {self.key!r} sem pacote definido")
        if not self.command:
            raise ValueError(f"interface {self.key!r} sem comando definido")
