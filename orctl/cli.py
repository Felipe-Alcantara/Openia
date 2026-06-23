"""orctl — launcher de interfaces de IA de terminal com OpenRouter.

Comandos:
    orctl list                  lista as interfaces suportadas
    orctl key set [CHAVE]       grava sua chave do OpenRouter (com segurança)
    orctl key show              mostra se há chave configurada (mascarada)
    orctl install <interface>   instala a interface escolhida
    orctl run <interface> ...   roda a interface (instala antes se faltar)
    orctl                       menu interativo para escolher e iniciar

A escolha do modelo é feita dentro de cada CLI; o orctl cuida de instalar,
configurar a chave e abrir a ferramenta certa.
"""

from __future__ import annotations

import sys

import typer

from . import config, runner
from .interfaces import registry
from .interfaces.base import AIInterface, Ecosystem

app = typer.Typer(
    add_completion=False,
    help="Launcher de CLIs de IA com OpenRouter. Rode sem argumentos para o menu.",
    no_args_is_help=False,
)
key_app = typer.Typer(help="Gerencia a chave do OpenRouter.")
app.add_typer(key_app, name="key")


def _err(msg: str) -> typer.Exit:
    """Imprime erro em vermelho e devolve um Exit(1) para o chamador levantar."""
    typer.secho(f"erro: {msg}", fg=typer.colors.RED, err=True)
    return typer.Exit(code=1)


def _mask(key: str) -> str:
    """Mascara a chave para exibição segura em logs/terminal."""
    if len(key) <= 12:
        return "*" * len(key)
    return f"{key[:8]}…{key[-4:]}"


def _resolve(interface_key: str) -> AIInterface:
    try:
        return registry.get(interface_key)
    except KeyError as exc:
        raise _err(str(exc)) from exc


def _ensure_key() -> str:
    """Carrega a chave ou orienta o usuário a configurá-la."""
    api_key = config.load_api_key()
    if not api_key:
        raise _err(
            "nenhuma chave do OpenRouter configurada. "
            "Rode 'orctl key set' ou exporte OPENROUTER_API_KEY."
        )
    return api_key


def _install_with_consent(iface: AIInterface) -> None:
    """Instala a interface, pedindo confirmação extra se for via script remoto.

    Instaladores SCRIPT baixam e executam código remoto (curl | bash); por isso
    exigem um "sim" explícito do usuário antes de prosseguir.
    """
    allow_script = False
    if iface.ecosystem is Ecosystem.SCRIPT:
        typer.secho(
            f"{iface.name} instala executando um script remoto:\n"
            f"    curl -fsSL {iface.install_script} | bash",
            fg=typer.colors.YELLOW,
        )
        if not typer.confirm("Confia nessa fonte e quer continuar?", default=False):
            raise typer.Exit()
        allow_script = True
    try:
        runner.install(iface, allow_script=allow_script)
    except runner.ToolingError as exc:
        raise _err(str(exc)) from exc


def _show_setup_hint(iface: AIInterface) -> None:
    """Mostra o passo de configuração próprio da ferramenta, quando houver."""
    if iface.setup_hint:
        typer.secho(
            f"\n{iface.name} precisa de um passo de configuração único:",
            fg=typer.colors.YELLOW,
        )
        typer.echo(iface.setup_hint)


@app.command("list")
def list_interfaces() -> None:
    """Lista todas as interfaces de IA suportadas."""
    typer.secho("Interfaces de IA suportadas:\n", bold=True)
    for iface in registry.all_interfaces():
        marca = "✓ instalada" if runner.is_installed(iface) else "· não instalada"
        typer.secho(f"  {iface.key}", fg=typer.colors.CYAN, bold=True, nl=False)
        typer.echo(f"  ({iface.name}) — {marca}")
        typer.echo(f"      {iface.description}")
        typer.echo(f"      {iface.homepage}")
    typer.echo("\nUse 'orctl run <chave>' para iniciar uma delas.")


@key_app.command("set")
def key_set(
    chave: str = typer.Argument(
        None, help="A chave do OpenRouter. Se omitida, é pedida sem ecoar na tela."
    ),
) -> None:
    """Grava a chave do OpenRouter no .env local (chmod 600)."""
    if not chave:
        chave = typer.prompt("Chave do OpenRouter", hide_input=True)
    try:
        path = config.save_api_key(chave)
    except ValueError as exc:
        raise _err(str(exc)) from exc
    typer.secho(f"chave salva em {path} (permissão 600).", fg=typer.colors.GREEN)


@key_app.command("show")
def key_show() -> None:
    """Mostra (mascarada) se há chave configurada e de onde vem."""
    api_key = config.load_api_key()
    if not api_key:
        typer.echo("nenhuma chave configurada.")
        return
    typer.echo(f"chave configurada: {_mask(api_key)}")


@app.command("install")
def install(interface: str = typer.Argument(..., help="Chave da interface, ex.: orchat")) -> None:
    """Instala a interface escolhida direto no sistema."""
    iface = _resolve(interface)
    if runner.is_installed(iface):
        typer.echo(f"{iface.name} já está instalada.")
        return
    typer.echo(f"instalando {iface.name} …")
    _install_with_consent(iface)
    typer.secho(f"{iface.name} instalada.", fg=typer.colors.GREEN)
    _show_setup_hint(iface)


@app.command(
    "run",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def run(
    ctx: typer.Context,
    interface: str = typer.Argument(..., help="Chave da interface, ex.: orchat"),
) -> None:
    """Roda a interface (instala antes, se necessário). Args extras vão para a CLI."""
    iface = _resolve(interface)
    api_key = _ensure_key()

    if not runner.is_installed(iface):
        typer.echo(f"{iface.name} não instalada; instalando antes de rodar …")
        _install_with_consent(iface)
        _show_setup_hint(iface)

    try:
        code = runner.run(iface, api_key, extra_args=list(ctx.args))
    except runner.ToolingError as exc:
        raise _err(str(exc)) from exc
    raise typer.Exit(code=code)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Sem subcomando: abre o menu interativo de escolha."""
    if ctx.invoked_subcommand is not None:
        return
    _interactive_menu()


def _interactive_menu() -> None:
    """Menu simples: escolher uma interface, garantir chave/instalação e rodar."""
    interfaces = registry.all_interfaces()
    typer.secho("orctl — escolha uma interface de IA:\n", bold=True)
    for idx, iface in enumerate(interfaces, start=1):
        marca = "✓" if runner.is_installed(iface) else " "
        typer.echo(f"  [{idx}] ({marca}) {iface.name} — {iface.description}")
    typer.echo("  [0] sair\n")

    escolha = typer.prompt("número", type=int, default=0)
    if escolha == 0:
        raise typer.Exit()
    if not 1 <= escolha <= len(interfaces):
        raise _err(f"opção inválida: {escolha}")

    iface = interfaces[escolha - 1]
    api_key = _ensure_key()

    if not runner.is_installed(iface):
        if not typer.confirm(f"{iface.name} não está instalada. Instalar agora?", default=True):
            raise typer.Exit()
        _install_with_consent(iface)
        _show_setup_hint(iface)

    typer.secho(f"\niniciando {iface.name} …\n", fg=typer.colors.GREEN)
    try:
        code = runner.run(iface, api_key)
    except runner.ToolingError as exc:
        raise _err(str(exc)) from exc
    raise typer.Exit(code=code)


def entrypoint() -> None:
    """Ponto de entrada para ``python -m orctl`` e para o script de console."""
    app()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())  # type: ignore[func-returns-value]
