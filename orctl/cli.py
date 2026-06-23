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

from . import config, models, runner, ui
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


def _pick_from(titulo: str, itens: list[str]) -> int | None:
    """Mostra uma lista numerada estilizada; devolve o índice (ou None p/ voltar)."""
    ui.section(titulo)
    for idx, item in enumerate(itens, start=1):
        ui.option(idx, item)
    ui.back_option(0, "voltar / pular")
    escolha = ui.ask_number()
    if escolha == 0:
        return None
    if not 1 <= escolha <= len(itens):
        ui.error(f"opção inválida: {escolha}")
        return _pick_from(titulo, itens)
    return escolha - 1


def _choose_model(iface: AIInterface) -> str | None:
    """Fluxo empresa → modelo. Devolve o id do modelo, ou None se pular.

    Carrega o catálogo do OpenRouter (com cache). Se a lista não puder ser
    obtida, avisa e segue sem modelo, em vez de travar o início da ferramenta.
    """
    try:
        catalogo = models.load_models()
    except models.CatalogError as exc:
        ui.warn(f"não deu para listar modelos: {exc}")
        ui.info("seguindo sem escolher modelo (a ferramenta usa o padrão dela).")
        return None

    vendors = models.vendors(catalogo)
    v_idx = _pick_from("🏢 Escolha a empresa:", vendors)
    if v_idx is None:
        return None
    vendor = vendors[v_idx]

    candidatos = models.models_of(catalogo, vendor)
    rotulos = [f"{_price_label(m)}  {m.name}  ({m.id})" for m in candidatos]
    m_idx = _pick_from(
        f"🧬 Modelos de {vendor} (do mais caro ao mais barato, US$/M tokens de saída):",
        rotulos,
    )
    if m_idx is None:
        return None
    return candidatos[m_idx].id


def _price_label(model: "models.Model") -> str:
    """Rótulo de preço de saída por milhão de tokens; 'free' quando 0."""
    if model.completion_price <= 0:
        return "  free  "
    return f"${model.completion_price * 1_000_000:6.2f}/M"


def _apply_or_explain_model(iface: AIInterface, model_id: str | None) -> str | None:
    """Decide como o modelo será usado e informa o usuário.

    Retorna o ``model_id`` a passar ao runner (quando aplicável por flag/env), ou
    None quando a ferramenta só aceita escolha na própria UI — caso em que mostra
    o ref pronto para o usuário colar lá.
    """
    if not model_id:
        return None
    if iface.supports_model_selection():
        ui.success(f"modelo: {iface.model_ref(model_id)} (aplicado automaticamente)")
        return model_id
    # Seleção dentro do app: instruir, não passar flag que pode não funcionar.
    ui.warn(f"{iface.name} escolhe o modelo na própria interface. Use lá dentro:")
    typer.secho(f"      {iface.model_ref(model_id)}", fg=typer.colors.BRIGHT_WHITE, bold=True)
    return None


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
    """Grava a chave do OpenRouter no .env local (permissão restrita no Unix)."""
    if not chave:
        chave = typer.prompt("Chave do OpenRouter", hide_input=True)
    try:
        path, warning = config.save_api_key(chave)
    except ValueError as exc:
        raise _err(str(exc)) from exc
    typer.secho(f"chave salva em {path}.", fg=typer.colors.GREEN)
    if warning:
        typer.secho(f"atenção: {warning}", fg=typer.colors.YELLOW)


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
    model: str = typer.Option(
        None, "--model", "-m",
        help="Id do modelo (empresa/modelo). Se omitido, abre o seletor empresa→modelo.",
    ),
    no_model: bool = typer.Option(
        False, "--no-model", help="Não escolher modelo; usa o padrão da ferramenta."
    ),
    subscription: bool = typer.Option(
        False, "--subscription",
        help="Rodar na autenticação própria da ferramenta (ex.: assinatura do Claude Code).",
    ),
    provider: bool = typer.Option(
        False, "--provider", help="Rodar via OpenRouter (padrão para a maioria)."
    ),
) -> None:
    """Roda a interface (instala antes, se necessário). Args extras vão para a CLI."""
    iface = _resolve(interface)

    if not runner.is_installed(iface):
        typer.echo(f"{iface.name} não instalada; instalando antes de rodar …")
        _install_with_consent(iface)
        _show_setup_hint(iface)

    use_provider = _decide_mode(iface, subscription=subscription, provider=provider)

    api_key = _ensure_key() if use_provider else None
    model_id = _decide_model(iface, model=model, no_model=no_model) if use_provider else None

    try:
        code = runner.run(
            iface, api_key, extra_args=list(ctx.args),
            model_id=model_id, use_provider=use_provider,
        )
    except runner.ToolingError as exc:
        raise _err(str(exc)) from exc
    raise typer.Exit(code=code)


def _decide_mode(iface: AIInterface, subscription: bool, provider: bool) -> bool:
    """Decide se roda via OpenRouter (True) ou na autenticação própria (False).

    Flags explícitas vencem. Se a ferramenta não suporta assinatura, é sempre
    provider. Caso suporte e nada tenha sido dito, pergunta ao usuário.
    """
    if not iface.supports_subscription:
        return True
    if subscription and provider:
        raise _err("escolha apenas um: --subscription ou --provider.")
    if subscription:
        return False
    if provider:
        return True
    idx = _pick_from(
        f"Como autenticar o {iface.name}?",
        [
            "🔑 OpenRouter (sua chave)",
            "👤 Assinatura / login próprio da ferramenta",
        ],
    )
    # Voltar/None mantém o padrão mais comum (OpenRouter).
    return idx != 1


def _decide_model(iface: AIInterface, model: str | None, no_model: bool) -> str | None:
    """Resolve qual modelo usar: flag explícita, seletor interativo, ou nenhum."""
    if no_model:
        return None
    chosen = model if model else _choose_model(iface)
    return _apply_or_explain_model(iface, chosen)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Sem subcomando: abre o menu interativo de escolha."""
    if ctx.invoked_subcommand is not None:
        return
    _interactive_menu()


def _interactive_menu() -> None:
    """Menu principal em loop: tudo pelo teclado, sem precisar de flags."""
    while True:
        interfaces = registry.all_interfaces()
        tem_chave = config.load_api_key() is not None

        ui.banner("orctl", "interfaces de IA no terminal · OpenRouter")
        ui.section("Escolha uma interface")
        for idx, iface in enumerate(interfaces, start=1):
            instalada = runner.is_installed(iface)
            status = (
                typer.style("instalada", fg=typer.colors.GREEN)
                if instalada else typer.style("não instalada", fg=typer.colors.BRIGHT_BLACK)
            )
            ui.option(idx, f"{iface.name} · {status}", emoji=iface.emoji,
                      dim=iface.description)

        ui.section("Configurações")
        estado_chave = (
            typer.style("configurada", fg=typer.colors.GREEN)
            if tem_chave else typer.style("não configurada", fg=typer.colors.YELLOW)
        )
        ui.option(len(interfaces) + 1, f"Chave do OpenRouter · {estado_chave}", emoji="🔑")
        ui.back_option(0, "sair")

        escolha = ui.ask_number()
        if escolha == 0:
            ui.info("até a próxima! 👋", emoji="")
            return
        if escolha == len(interfaces) + 1:
            _menu_set_key()
            continue
        if not 1 <= escolha <= len(interfaces):
            ui.error(f"opção inválida: {escolha}")
            continue

        _run_interface_flow(interfaces[escolha - 1])


def _menu_set_key() -> None:
    """Configura a chave do OpenRouter sem sair do menu."""
    chave = typer.prompt(typer.style("🔑 Cole sua chave do OpenRouter", fg=typer.colors.CYAN),
                         hide_input=True)
    try:
        path, warning = config.save_api_key(chave)
    except ValueError as exc:
        ui.error(str(exc))
        return
    ui.success(f"chave salva em {path}.")
    if warning:
        ui.warn(warning)


def _run_interface_flow(iface: AIInterface) -> None:
    """Instala (se preciso), escolhe modo/modelo e roda a interface escolhida."""
    if not runner.is_installed(iface):
        ui.warn(f"{iface.name} ainda não está instalada.")
        if not typer.confirm("  instalar agora?", default=True):
            return
        try:
            _install_with_consent(iface)
        except typer.Exit:
            return
        _show_setup_hint(iface)

    use_provider = _decide_mode(iface, subscription=False, provider=False)

    api_key = None
    model_id = None
    if use_provider:
        if config.load_api_key() is None:
            ui.warn("você ainda não configurou a chave do OpenRouter.")
            _menu_set_key()
            if config.load_api_key() is None:
                return
        api_key = config.load_api_key()
        if typer.confirm("  escolher o modelo agora (empresa → modelo)?", default=True):
            model_id = _apply_or_explain_model(iface, _choose_model(iface))
    else:
        ui.success(f"usando a autenticação própria do {iface.name} (sem OpenRouter).")

    ui.banner(f"{iface.emoji}  iniciando {iface.name}")
    try:
        runner.run(iface, api_key, model_id=model_id, use_provider=use_provider)
    except runner.ToolingError as exc:
        ui.error(str(exc))
        return
    ui.info("a sessão terminou — voltando ao menu.", emoji="↩️")


def entrypoint() -> None:
    """Ponto de entrada para ``python -m orctl`` e para o script de console."""
    app()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())  # type: ignore[func-returns-value]
