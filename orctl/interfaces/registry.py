"""Registro das interfaces de IA suportadas.

Para adicionar uma nova CLI, basta acrescentar uma ``AIInterface`` em
``_INTERFACES``. Nada no núcleo precisa mudar.

As interfaces aqui foram escolhidas por (a) serem usáveis no terminal e
(b) falarem com o OpenRouter, seja nativamente, seja pelo protocolo
compatível com OpenAI (base_url + chave).
"""

from __future__ import annotations

from .base import AIInterface, Ecosystem

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Ordem aqui = ordem de exibição no menu.
_INTERFACES: tuple[AIInterface, ...] = (
    AIInterface(
        key="orchat",
        name="OrChat",
        description="Chat rico no terminal: streaming, contagem de tokens e resumo de conversa.",
        ecosystem=Ecosystem.PYTHON,
        package="orchat",
        command="orchat",
        homepage="https://github.com/oop7/OrChat",
        env_keys=("OPENROUTER_API_KEY",),
        # OrChat escolhe o modelo na própria interface; orctl mostra o escolhido.
        model_select_in_app=True,
    ),
    AIInterface(
        key="aichat",
        name="aichat",
        description="CLI/REPL de chat genérica e leve; aceita qualquer provedor OpenAI-compatível.",
        ecosystem=Ecosystem.PYTHON,
        package="aichat",
        command="aichat",
        homepage="https://github.com/sigoden/aichat",
        env_keys=("OPENAI_API_KEY",),
        base_url_env="OPENAI_API_BASE",
        # aichat usa formato próprio (provider:model), não o id cru do OpenRouter;
        # então o modelo é aplicado por instrução, não por flag automática.
        model_select_in_app=True,
    ),
    AIInterface(
        key="llm",
        name="llm (Simon Willison)",
        description="CLI de LLM extensível, com plugins, logs em SQLite e modo conversa.",
        ecosystem=Ecosystem.PYTHON,
        package="llm",
        command="llm",
        homepage="https://github.com/simonw/llm",
        env_keys=("OPENAI_API_KEY",),
        base_url_env="OPENAI_BASE_URL",
        # llm registra modelos por alias na config; aplicado por instrução.
        model_select_in_app=True,
    ),
    # --- Agentes de código (leem/editam arquivos e rodam comandos) ---
    AIInterface(
        key="cline",
        name="Cline",
        description="Agente de código autônomo no terminal; provider OpenRouter nativo.",
        ecosystem=Ecosystem.NODE,
        package="cline",
        command="cline",
        homepage="https://github.com/cline/cline",
        env_keys=("OPENROUTER_API_KEY",),
        # cline -m aceita o id do OpenRouter direto.
        model_arg="-m",
    ),
    AIInterface(
        key="opencode",
        name="opencode",
        description="Agente de código no terminal; OpenRouter via base_url OpenAI-compatível.",
        ecosystem=Ecosystem.SCRIPT,
        package="",  # instalado por script oficial, não por pip/npm
        command="opencode",
        homepage="https://opencode.ai",
        install_script="https://opencode.ai/install",
        env_keys=("OPENAI_API_KEY",),
        base_url_env="OPENAI_API_BASE",
        # opencode --model usa exatamente o id provider/model do OpenRouter.
        model_arg="--model",
    ),
    AIInterface(
        key="openclaw",
        name="OpenClaw",
        description="Assistente/agente autônomo com suporte nativo a OpenRouter.",
        ecosystem=Ecosystem.NODE,
        package="openclaw",
        command="openclaw",
        homepage="https://github.com/openclaw/openclaw",
        env_keys=("OPENROUTER_API_KEY",),
        setup_hint=(
            "Na primeira vez, configure a chave rodando:\n"
            "    openclaw onboard --auth-choice apiKey "
            "--token-provider openrouter --token \"$OPENROUTER_API_KEY\""
        ),
        # OpenClaw referencia modelos como openrouter/<empresa>/<modelo>, escolhidos
        # no onboard/UI; orctl mostra o ref pronto.
        model_prefix="openrouter/",
        model_select_in_app=True,
    ),
)

_BY_KEY: dict[str, AIInterface] = {iface.key: iface for iface in _INTERFACES}


def all_interfaces() -> tuple[AIInterface, ...]:
    """Retorna todas as interfaces registradas, na ordem de exibição."""
    return _INTERFACES


def get(key: str) -> AIInterface:
    """Busca uma interface pela chave.

    Levanta ``KeyError`` com mensagem clara se a chave não existir, para que o
    chamador traduza num erro de CLI previsível.
    """
    try:
        return _BY_KEY[key]
    except KeyError as exc:
        disponiveis = ", ".join(sorted(_BY_KEY))
        raise KeyError(
            f"interface desconhecida: {key!r}. Disponíveis: {disponiveis}"
        ) from exc
