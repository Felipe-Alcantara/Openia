#!/usr/bin/env python3
"""
start_app.py — Script padrao de inicializacao (Felixo System Design).

Ponto de entrada unico do openia: instala dependencias e abre o menu interativo
para escolher e iniciar uma interface de IA com OpenRouter. Pensado para quem
nao tem familiaridade com terminal — basta um comando:

    python start_app.py

A interface e sempre o menu interativo: instalar/configurar/iniciar/ver status
acontecem todos por ele, sem decorar argumento. As flags abaixo existem so como
atalho avancado e nao sao necessarias para uso normal:

    python start_app.py --no-install   # pula a checagem/instalacao de deps
    python start_app.py key add        # repassado ao openia (atalho)
    python start_app.py list           # repassado ao openia (atalho)

Adaptacao do contrato GUIA-START-APP-SCRIPT.md: este projeto e uma CLI
interativa, nao um servidor web. Por isso nao ha porta, "restart" nem abertura
de navegador — o equivalente a "iniciar o app e abrir" e abrir o menu do openia.
O que se aplica do contrato esta mantido: menu interativo como porta de entrada,
instalar dependencias, ponto de entrada unico, cross-platform, falhar com
mensagem clara e nao guardar segredo (a chave fica em openia/keys.json,
gitignored, nunca neste script).
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Dependencias minimas para rodar o openia (declaradas no pyproject).
REQUIRED = ("typer",)

# Flags consumidas pelo proprio start_app; o resto e repassado ao openia.
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
    # Separa a flag deste script dos argumentos destinados ao openia.
    argv = sys.argv[1:]
    do_install = NO_INSTALL_FLAG not in argv
    openia_args = [a for a in argv if a != NO_INSTALL_FLAG]

    if do_install and not install_deps():
        return 1

    # Garante que o pacote local seja importavel mesmo fora da raiz.
    sys.path.insert(0, str(ROOT))
    try:
        from openia.cli import app, force_utf8_output
    except ImportError as exc:
        log(f"Nao consegui carregar o openia: {exc}")
        log("Confirme que voce esta rodando este script na raiz do projeto.")
        return 1

    # Saida UTF-8 no terminal (Windows usa cp1252 e quebraria com '✓'/emojis).
    force_utf8_output()

    # Sem argumentos: abre o menu interativo. Com argumentos: repassa ao openia
    # (ex.: 'key', 'list', 'run orchat'), mantendo um unico ponto de entrada.
    try:
        app(args=openia_args, prog_name="start_app.py", standalone_mode=False)
        return 0
    except SystemExit as exc:  # Typer/Click sinalizam saida por excecao
        return int(exc.code or 0)
    except KeyboardInterrupt:
        log("Encerrado pelo usuario.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
