"""Gerenciamento da chave do OpenRouter e do ambiente de execução.

Decisões de segurança (ver README/IA.md):
- A chave nunca aparece em código nem em arquivo versionado.
- É persistida em ``orctl/.env`` com permissão 0600 (somente o dono lê/escreve).
- Esse arquivo está no ``.gitignore``.
- Na hora de rodar uma CLI, a chave é repassada via variável de ambiente do
  processo filho — não fica em histórico de shell nem em argumentos.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from .interfaces.base import AIInterface
from .interfaces.registry import OPENROUTER_BASE_URL

ENV_FILENAME = ".env"
ENV_VAR = "OPENROUTER_API_KEY"

# O .env vive ao lado deste módulo, dentro de orctl/.
_ENV_PATH = Path(__file__).resolve().parent / ENV_FILENAME


def env_path() -> Path:
    """Caminho do arquivo .env onde a chave é guardada."""
    return _ENV_PATH


def _parse_env(text: str) -> dict[str, str]:
    """Lê pares CHAVE=valor de um .env simples, ignorando comentários/brancos."""
    data: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        data[name.strip()] = value.strip()
    return data


def load_api_key() -> str | None:
    """Carrega a chave do .env, ou ``None`` se ainda não foi configurada.

    Uma variável de ambiente já exportada tem prioridade sobre o arquivo, para
    permitir sobrescrever em CI ou sessões temporárias sem editar o disco.
    """
    from_env = os.environ.get(ENV_VAR)
    if from_env:
        return from_env.strip() or None

    if not _ENV_PATH.exists():
        return None
    parsed = _parse_env(_ENV_PATH.read_text(encoding="utf-8"))
    value = parsed.get(ENV_VAR, "").strip()
    return value or None


def validate_api_key(key: str) -> str:
    """Valida o formato básico de uma chave do OpenRouter.

    Não chama a rede aqui (validação real acontece quando a CLI roda); apenas
    rejeita entradas obviamente inválidas para dar erro cedo e claro.
    """
    key = key.strip()
    if not key:
        raise ValueError("a chave não pode ser vazia")
    if not key.startswith("sk-or-"):
        raise ValueError(
            "isso não parece uma chave do OpenRouter "
            "(o esperado começa com 'sk-or-')"
        )
    if len(key) < 20:
        raise ValueError("a chave parece curta demais para ser válida")
    return key


def save_api_key(key: str) -> Path:
    """Persiste a chave no .env com permissão 0600. Retorna o caminho gravado."""
    key = validate_api_key(key)
    content = (
        "# Arquivo gerado pelo orctl. NÃO versionar.\n"
        f"{ENV_VAR}={key}\n"
    )
    _ENV_PATH.write_text(content, encoding="utf-8")
    # 0600: somente o dono lê e escreve.
    _ENV_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return _ENV_PATH


def build_run_env(interface: AIInterface, api_key: str) -> dict[str, str]:
    """Monta o ambiente para executar uma interface.

    Parte do ambiente atual e injeta a chave do OpenRouter em todas as variáveis
    que aquela ferramenta espera, além da base_url quando aplicável.
    """
    env = dict(os.environ)
    env[ENV_VAR] = api_key
    for alias in interface.env_keys:
        env[alias] = api_key
    if interface.base_url_env:
        env[interface.base_url_env] = interface.base_url or OPENROUTER_BASE_URL
    # Esvazia variáveis que conflitam com a forma de autenticação da ferramenta.
    for name in interface.clear_env:
        env[name] = ""
    return env
