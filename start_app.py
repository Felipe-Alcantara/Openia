#!/usr/bin/env python3
"""
start_app.py — Script padrao de inicializacao (Felixo System Design).

Ponto de entrada unico do orctl: instala dependencias e abre o menu para
escolher e iniciar uma interface de IA com OpenRouter. Pensado para quem nao
tem familiaridade com terminal — basta:

    python start_app.py

Uso:
    python start_app.py                # instala (se preciso) + abre o menu
    python start_app.py --no-install   # pula a instalacao de dependencias
    python start_app.py key            # configura a chave do OpenRouter
    python start_app.py list           # lista as interfaces suportadas

Adaptacao do contrato GUIA-START-APP-SCRIPT.md: este projeto e uma CLI
interativa, nao um servidor web. Por isso nao ha porta, "restart" nem abertura
de navegador — o equivalente a "iniciar o app e abrir" e abrir o menu do orctl.
O que se aplica do contrato esta mantido: instalar dependencias, ponto de
entrada unico, cross-platform, falhar com mensagem clara e nao guardar segredo
(a chave fica em orctl/.env, nunca neste script).
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Dependencias minimas para rodar o orctl (declaradas no pyproject).
REQUIRED = ("typer",)

# Flags consumidas pelo proprio start_app; o resto e repassado ao orctl.
NO_INSTALL_FLAG = "--no-install"


def log(msg: str) -> None:
    print(f"[start_app] {msg}", flush=True)


def missing_deps() -> list[str]:
    """Retorna as dependencias ausentes, sem importar nada pesado."""
    from importlib.util import find_spec

    return [pkg for pkg in REQUIRED if find_spec(pkg) is None]


def install_deps() -> bool:
    """Instala as dependencias ausentes. Retorna True se tudo ficou disponivel."""
    faltando = missing_deps()
    if not faltando:
        return True

    log(f"Instalando dependencias: {', '.join(faltando)} ...")
    cmd = [sys.executable, "-m", "pip", "install", *faltando]
    result = subprocess.run(cmd)
    if result.returncode != 0:
        log(
            "Falha ao instalar dependencias. Tente manualmente:\n"
            f"    {sys.executable} -m pip install {' '.join(faltando)}"
        )
        return False
    if missing_deps():
        log("As dependencias ainda nao foram encontradas apos a instalacao.")
        return False
    return True


def main() -> int:
    # Separa a flag deste script dos argumentos destinados ao orctl.
    argv = sys.argv[1:]
    do_install = NO_INSTALL_FLAG not in argv
    orctl_args = [a for a in argv if a != NO_INSTALL_FLAG]

    if do_install and not install_deps():
        return 1

    # Garante que o pacote local seja importavel mesmo fora da raiz.
    sys.path.insert(0, str(ROOT))
    try:
        from orctl.cli import app
    except ImportError as exc:
        log(f"Nao consegui carregar o orctl: {exc}")
        log("Confirme que voce esta rodando este script na raiz do projeto.")
        return 1

    # Sem argumentos: abre o menu interativo. Com argumentos: repassa ao orctl
    # (ex.: 'key', 'list', 'run orchat'), mantendo um unico ponto de entrada.
    try:
        app(args=orctl_args, prog_name="start_app.py", standalone_mode=False)
        return 0
    except SystemExit as exc:  # Typer/Click sinalizam saida por excecao
        return int(exc.code or 0)
    except KeyboardInterrupt:
        log("Encerrado pelo usuario.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
