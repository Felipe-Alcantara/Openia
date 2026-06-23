"""Gerenciamento das chaves do OpenRouter e do ambiente de execução.

Decisões de segurança (ver README/IA.md):
- As chaves nunca aparecem em código nem em arquivo versionado.
- São persistidas em ``orctl/keys.json`` com permissão 0600 no Unix (só o dono
  lê/escreve); no Windows isso não se aplica e o usuário é avisado.
- Esse arquivo está no ``.gitignore``.
- Na hora de rodar uma CLI, a chave é repassada via variável de ambiente do
  processo filho — não fica em histórico de shell nem em argumentos.

Suporta várias chaves nomeadas, com uma marcada como ativa. Uma variável de
ambiente ``OPENROUTER_API_KEY`` já exportada tem prioridade sobre o arquivo,
para uso temporário em CI/sessões sem editar o disco.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from .interfaces.base import AIInterface
from .interfaces.registry import OPENROUTER_BASE_URL

ENV_VAR = "OPENROUTER_API_KEY"

_DIR = Path(__file__).resolve().parent
_KEYS_PATH = _DIR / "keys.json"
# Arquivo antigo de chave única; migrado automaticamente se existir.
_LEGACY_ENV_PATH = _DIR / ".env"


@dataclass(frozen=True)
class NamedKey:
    """Uma chave do OpenRouter com um nome amigável."""

    name: str
    key: str


# --------------------------------------------------------------------------
# Validação
# --------------------------------------------------------------------------
def validate_api_key(key: str) -> str:
    """Valida o formato básico de uma chave do OpenRouter.

    Não chama a rede (validação real acontece quando a CLI roda); apenas rejeita
    entradas obviamente inválidas para dar erro cedo e claro.
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


def validate_name(name: str) -> str:
    """Valida o nome amigável de uma chave."""
    name = name.strip()
    if not name:
        raise ValueError("o nome não pode ser vazio")
    if len(name) > 40:
        raise ValueError("o nome é longo demais (máx. 40 caracteres)")
    return name


# --------------------------------------------------------------------------
# Persistência (keys.json) + migração do .env antigo
# --------------------------------------------------------------------------
def _restrict_permissions() -> str | None:
    """Aplica 0600 no Unix; devolve aviso no Windows (onde não se aplica)."""
    if os.name == "nt":
        return (
            "no Windows o arquivo não fica protegido por permissão de SO; "
            "mantenha esta pasta privada e confie no .gitignore para não versioná-lo."
        )
    _KEYS_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return None


def _read_store() -> dict:
    """Lê o keys.json; migra o .env antigo na primeira vez, se houver."""
    if _KEYS_PATH.exists():
        try:
            data = json.loads(_KEYS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "keys" in data:
                return data
        except (json.JSONDecodeError, OSError):
            pass  # arquivo corrompido: trata como vazio, não derruba o programa
        return {"active": None, "keys": {}}

    migrated = _migrate_legacy_env()
    if migrated:
        return migrated
    return {"active": None, "keys": {}}


def _migrate_legacy_env() -> dict | None:
    """Converte um ``.env`` de chave única em store, se existir e for válido."""
    if not _LEGACY_ENV_PATH.exists():
        return None
    for raw in _LEGACY_ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith(f"{ENV_VAR}="):
            value = line.partition("=")[2].strip()
            if value:
                store = {"active": "padrão", "keys": {"padrão": value}}
                _write_store(store)
                return store
    return None


def _write_store(store: dict) -> str | None:
    """Grava o store e restringe permissões. Retorna aviso (Windows) ou None."""
    _KEYS_PATH.write_text(json.dumps(store, indent=2), encoding="utf-8")
    return _restrict_permissions()


# --------------------------------------------------------------------------
# API pública de chaves
# --------------------------------------------------------------------------
def list_keys() -> list[NamedKey]:
    """Todas as chaves cadastradas, em ordem de nome."""
    store = _read_store()
    return [NamedKey(name=n, key=k) for n, k in sorted(store["keys"].items())]


def active_key_name() -> str | None:
    """Nome da chave ativa, ou None se não houver chaves."""
    return _read_store().get("active")


def load_api_key() -> str | None:
    """Retorna a chave ativa (ou a da env var, que tem prioridade).

    Mantém a assinatura usada pelo restante do código: devolve só a string.
    """
    from_env = os.environ.get(ENV_VAR)
    if from_env and from_env.strip():
        return from_env.strip()

    store = _read_store()
    active = store.get("active")
    if active and active in store["keys"]:
        return store["keys"][active]
    return None


def add_key(name: str, key: str, make_active: bool = True) -> str | None:
    """Adiciona/atualiza uma chave nomeada. Retorna aviso de permissão ou None."""
    name = validate_name(name)
    key = validate_api_key(key)
    store = _read_store()
    store["keys"][name] = key
    if make_active or store.get("active") is None:
        store["active"] = name
    return _write_store(store)


def set_active(name: str) -> None:
    """Marca uma chave existente como ativa."""
    store = _read_store()
    if name not in store["keys"]:
        raise ValueError(f"não existe chave chamada {name!r}.")
    store["active"] = name
    _write_store(store)


def rename_key(old: str, new: str) -> None:
    """Renomeia uma chave, preservando se ela era a ativa."""
    new = validate_name(new)
    store = _read_store()
    if old not in store["keys"]:
        raise ValueError(f"não existe chave chamada {old!r}.")
    if new in store["keys"] and new != old:
        raise ValueError(f"já existe uma chave chamada {new!r}.")
    store["keys"][new] = store["keys"].pop(old)
    if store.get("active") == old:
        store["active"] = new
    _write_store(store)


def remove_key(name: str) -> None:
    """Remove uma chave; se era a ativa, escolhe outra (ou nenhuma)."""
    store = _read_store()
    if name not in store["keys"]:
        raise ValueError(f"não existe chave chamada {name!r}.")
    del store["keys"][name]
    if store.get("active") == name:
        store["active"] = next(iter(sorted(store["keys"])), None)
    _write_store(store)


def keys_path() -> Path:
    """Caminho do arquivo onde as chaves são guardadas."""
    return _KEYS_PATH


# --------------------------------------------------------------------------
# Ambiente de execução
# --------------------------------------------------------------------------
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
