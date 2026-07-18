"""openia — launcher de interfaces de IA de terminal com OpenRouter.

Comandos:
    openia list                  lista as interfaces suportadas
    openia key add [NOME]        adiciona uma chave nomeada do OpenRouter e a ativa
    openia key use <NOME>        define qual chave fica ativa
    openia key list              lista as chaves cadastradas (mascaradas)
    openia install <interface>   instala a interface escolhida
    openia run <interface> ...   roda a interface (instala antes se faltar)
    openia                       menu interativo para escolher e iniciar

A escolha do modelo é feita dentro de cada CLI; o openia cuida de instalar,
configurar a chave e abrir a ferramenta certa.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable

import typer

from . import config, models, runner, ui, usage
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


class _Cancelado(Exception):
    """Sinaliza que o usuário escolheu voltar/cancelar num sub-passo do menu.

    Propaga até o fluxo da interface, que então retorna ao menu principal em vez
    de avançar. Evita tratar 'voltar' (0) como uma escolha implícita.
    """


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
            "Rode 'openia key set' ou exporte OPENROUTER_API_KEY."
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
    while True:
        ui.section(titulo)
        for idx, item in enumerate(itens, start=1):
            ui.option(idx, item)
        ui.back_option(0, "voltar / pular")
        escolha = ui.ask_number()
        if escolha == 0:
            return None
        if 1 <= escolha <= len(itens):
            return escolha - 1
        ui.error(f"opção inválida: {escolha}")


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
    typer.echo("\nUse 'openia run <chave>' para iniciar uma delas.")


@key_app.command("add")
def key_add(
    nome: str = typer.Argument(..., help="Nome amigável da chave, ex.: pessoal"),
    chave: str = typer.Argument(
        None, help="A chave do OpenRouter. Se omitida, é pedida sem ecoar na tela."
    ),
) -> None:
    """Adiciona uma chave nomeada e a torna ativa."""
    if not chave:
        chave = typer.prompt("Chave do OpenRouter", hide_input=True)
    try:
        warning = config.add_key(nome, chave)
    except ValueError as exc:
        raise _err(str(exc)) from exc
    ui.success(f"chave '{nome}' salva e ativada.")
    if warning:
        ui.warn(warning)


@key_app.command("list")
def key_list() -> None:
    """Lista as chaves cadastradas (mascaradas), marcando a ativa."""
    ativa = config.active_key_name()
    chaves = config.list_keys()
    if not chaves:
        typer.echo("nenhuma chave cadastrada.")
        return
    for nk in chaves:
        marca = "● ativa" if nk.name == ativa else "  "
        typer.echo(f"  {marca}  {nk.name}: {_mask(nk.key)}")


@key_app.command("use")
def key_use(nome: str = typer.Argument(..., help="Nome da chave a ativar")) -> None:
    """Define qual chave fica ativa."""
    try:
        config.set_active(nome)
    except ValueError as exc:
        raise _err(str(exc)) from exc
    ui.success(f"chave ativa agora é '{nome}'.")


@app.command("statusline", hidden=True)
def statusline() -> None:
    """Imprime uma linha de uso/saldo do OpenRouter (usada pelo Claude Code)."""
    api_key = config.load_api_key()
    if not api_key:
        typer.echo("openia: sem chave")
        return
    try:
        u = usage.fetch_usage(api_key, timeout=4.0)
    except usage.UsageError:
        # Statusline não pode travar a sessão; falha silenciosa e curta.
        typer.echo("openia: uso indisponível")
        return
    typer.echo(usage.format_line(u))


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
    directory: str = typer.Option(
        None, "--dir", "-C",
        help="Pasta onde rodar (raiz do projeto). Para agentes de código; "
             "se omitido, o openia pergunta.",
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
    cwd = _resolve_workdir(iface, directory)

    try:
        code = runner.run(
            iface, api_key, extra_args=list(ctx.args),
            model_id=model_id, use_provider=use_provider, cwd=cwd,
        )
    except runner.ToolingError as exc:
        raise _err(str(exc)) from exc
    raise typer.Exit(code=code)


def _resolve_workdir(iface: AIInterface, directory: str | None) -> str | None:
    """Resolve o cwd do comando ``run``: flag --dir, ou pergunta se for agente.

    Chats puros não usam cwd (None). Para agentes de código: respeita ``--dir``
    quando dado (validando), senão cai no fluxo interativo de ``_choose_workdir``.
    """
    if not iface.is_code_agent:
        return None
    if directory:
        from pathlib import Path

        alvo = Path(directory).expanduser()
        if not alvo.is_dir():
            raise _err(f"--dir não é uma pasta válida: {alvo}")
        return str(alvo.resolve())
    return _choose_workdir(iface)


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
    if idx is None:  # escolheu voltar
        raise _Cancelado
    return idx == 0  # [1] OpenRouter → provider; [2] assinatura → False


def _decide_model(iface: AIInterface, model: str | None, no_model: bool) -> str | None:
    """Resolve qual modelo usar: flag explícita, seletor interativo, ou nenhum."""
    if no_model:
        return None
    chosen = model if model else _choose_model(iface)
    return _apply_or_explain_model(iface, chosen)


def _choose_workdir(iface: AIInterface) -> str:
    """Pergunta em qual pasta o agente de código deve rodar (seu cwd).

    Agentes de código (Claude Code, opencode, cline…) usam o diretório de
    trabalho como raiz do projeto: é onde eles leem/editam arquivos. No Claude
    Code, esse caminho também indexa o histórico de sessões em
    ``~/.claude/projects/<caminho>`` — por isso, para o histórico da extensão do
    VS Code aparecer, o agente precisa rodar no MESMO caminho do repositório
    aberto no editor.

    Mostra o diretório atual como padrão (Enter aceita) e valida a pasta digitada.
    """
    from pathlib import Path

    atual = Path.cwd()
    ui.section("Em qual pasta o agente vai trabalhar?")
    ui.info(f"raiz do projeto = onde {iface.name} vai ler e editar arquivos.", emoji="📁")
    if iface.key == "claudecode":
        ui.warn(
            "o histórico do Claude Code é ligado à pasta do projeto. Para ver no "
            "menu /resume o mesmo histórico da extensão do VS Code, use aqui o "
            "MESMO caminho do repositório que você abre no editor."
        )
    typer.secho(f"  atual: {atual}", fg=typer.colors.BRIGHT_BLACK)

    while True:
        resposta = typer.prompt(
            typer.style("📁 Caminho do projeto (Enter = atual)", fg=typer.colors.CYAN),
            default=str(atual),
            show_default=False,
        ).strip()
        alvo = Path(resposta).expanduser()
        if not alvo.exists():
            ui.error(f"a pasta não existe: {alvo}")
            continue
        if not alvo.is_dir():
            ui.error(f"isso não é uma pasta: {alvo}")
            continue
        resolved = str(alvo.resolve())
        ui.success(f"o agente vai rodar em: {resolved}")
        return resolved


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
        ativa = config.active_key_name()

        ui.banner("openia", "interfaces de IA no terminal · OpenRouter")
        ui.section("Escolha uma interface")
        for idx, iface in enumerate(interfaces, start=1):
            instalada = runner.is_installed(iface)
            status = (
                typer.style("instalada", fg=typer.colors.GREEN)
                if instalada else typer.style("não instalada", fg=typer.colors.BRIGHT_BLACK)
            )
            ui.option(idx, f"{iface.name} · {status}", emoji=iface.emoji,
                      dim=iface.description)

        ui.section("Instalar e configurar")
        estado_chave = (
            typer.style(f"ativa: {ativa}", fg=typer.colors.GREEN)
            if ativa else typer.style("nenhuma chave", fg=typer.colors.YELLOW)
        )
        n = len(interfaces)
        ui.option(n + 1, "Instalar / Setup de uma interface", emoji="📦",
                  dim="instala uma CLI sem já iniciá-la")
        ui.option(n + 2, f"Chaves do OpenRouter · {estado_chave}", emoji="🔑",
                  dim="adicionar, ativar, renomear ou remover")

        ui.section("Status e uso")
        ui.option(n + 3, "Status do openia", emoji="🩺",
                  dim="o que está instalado, chave e dependências")
        ui.option(n + 4, "Ver meu uso/saldo no OpenRouter", emoji="📊")
        ui.option(n + 5, "Statusline de custo no Claude Code", emoji="🧾")
        ui.back_option(0, "sair")

        escolha = ui.ask_number()
        if escolha == 0:
            ui.info("até a próxima! 👋", emoji="")
            return
        if escolha == n + 1:
            _menu_install()
            continue
        if escolha == n + 2:
            _menu_keys()
            continue
        if escolha == n + 3:
            _menu_status()
            continue
        if escolha == n + 4:
            _menu_show_usage()
            continue
        if escolha == n + 5:
            _menu_statusline()
            continue
        if not 1 <= escolha <= n:
            ui.error(f"opção inválida: {escolha}")
            continue

        _run_interface_flow(interfaces[escolha - 1])


def _menu_install() -> None:
    """Instala/Setup uma interface sem já iniciá-la (ação Instalar/Setup do menu).

    Cumpre o passo "Instalar/Setup" do contrato GUIA-START-APP-SCRIPT: deixar a
    pessoa preparar uma ferramenta na frente, separado de rodá-la. Reaproveita o
    mesmo fluxo de consentimento do `run` (script remoto pede confirmação).
    """
    interfaces = registry.all_interfaces()
    rotulos = [
        f"{iface.name} · {'instalada' if runner.is_installed(iface) else 'não instalada'}"
        for iface in interfaces
    ]
    idx = _pick_from("Qual interface instalar?", rotulos)
    if idx is None:
        return
    iface = interfaces[idx]
    if runner.is_installed(iface):
        ui.info(f"{iface.name} já está instalada.", emoji="✅")
        return
    ui.banner(f"{iface.emoji}  instalando {iface.name}")
    try:
        _install_with_consent(iface)
    except typer.Exit:
        ui.info("instalação cancelada.", emoji="↩️")
        return
    ui.success(f"{iface.name} instalada.")
    _show_setup_hint(iface)


def _menu_status() -> None:
    """Mostra o estado real do openia (ação Status do contrato do start_app).

    Checa de verdade — dependência do menu, chave ativa e quais interfaces estão
    instaladas — em vez de chutar. É o "Status" exigido pelo menu mínimo.
    """
    from importlib.util import find_spec

    ui.section("Status do openia")

    typer_ok = find_spec("typer") is not None
    (ui.success if typer_ok else ui.warn)(
        f"dependência do menu (typer): {'disponível' if typer_ok else 'ausente'}"
    )

    ativa = config.active_key_name()
    total_chaves = len(config.list_keys())
    if ativa:
        ui.success(f"chave do OpenRouter: ativa '{ativa}' ({total_chaves} cadastrada(s))")
    else:
        ui.warn("chave do OpenRouter: nenhuma cadastrada")

    typer.echo()
    typer.secho("  Interfaces:", bold=True)
    for iface in registry.all_interfaces():
        instalada = runner.is_installed(iface)
        marca = (
            typer.style("✓ instalada", fg=typer.colors.GREEN)
            if instalada else typer.style("· não instalada", fg=typer.colors.BRIGHT_BLACK)
        )
        typer.echo(f"    {iface.emoji}  {iface.name}: {marca}")


def _menu_keys() -> None:
    """Submenu de gestão de chaves: adicionar, ativar, renomear, remover."""
    while True:
        ativa = config.active_key_name()
        chaves = config.list_keys()

        ui.section("Chaves do OpenRouter")
        for nk in chaves:
            marca = "● " if nk.name == ativa else "  "
            tag = typer.style("ativa", fg=typer.colors.GREEN) if nk.name == ativa else ""
            ui.option(0, f"{marca}{nk.name}  ({_mask(nk.key)})  {tag}".rstrip(), emoji="🔑")
        if not chaves:
            ui.info("nenhuma chave cadastrada ainda.", emoji="")
            ui.info("escolha '➕ Adicionar uma chave' — eu explico como criar uma.",
                    emoji="👉")

        opcoes = ["➕ Adicionar uma chave"]
        if chaves:
            opcoes.append("🌐 Testar uma chave")
        if len(chaves) > 1:
            opcoes.append("✅ Definir qual fica ativa")
        if chaves:
            opcoes += ["✏️  Renomear uma chave", "🗑️  Remover uma chave"]
        idx = _pick_from("O que deseja fazer?", opcoes)
        if idx is None:
            return
        acao = opcoes[idx]

        if acao.startswith("➕"):
            _key_add_flow()
        elif acao.startswith("🌐"):
            _key_pick_and(lambda nome: _testar_chave(
                next(nk.key for nk in config.list_keys() if nk.name == nome)))
        elif acao.startswith("✅"):
            _key_pick_and(lambda nome: (config.set_active(nome),
                                        ui.success(f"'{nome}' agora é a chave ativa.")))
        elif acao.startswith("✏️"):
            _key_rename_flow()
        elif acao.startswith("🗑️"):
            _key_pick_and(lambda nome: (config.remove_key(nome),
                                        ui.success(f"chave '{nome}' removida.")))


def _explain_how_to_get_key() -> None:
    """Mostra o passo a passo de como criar uma chave no OpenRouter.

    Pensado para quem nunca usou o serviço: leva da criação da conta até copiar
    a chave. Exibido antes de pedir a chave quando ainda não há nenhuma cadastrada.
    """
    ui.section("Como conseguir uma chave do OpenRouter")
    passos = [
        "Acesse https://openrouter.ai e crie uma conta (dá para entrar com Google/GitHub).",
        "Adicione créditos em https://openrouter.ai/credits "
        "(ou use modelos gratuitos, marcados com ':free').",
        "Abra https://openrouter.ai/keys e clique em 'Create Key'.",
        "Dê um nome à chave e clique em 'Create' — ela começa com 'sk-or-'.",
        "Copie a chave AGORA (ela só aparece uma vez) e cole aqui no próximo passo.",
    ]
    for i, passo in enumerate(passos, start=1):
        marca = typer.style(f"  {i}.", fg=typer.colors.GREEN, bold=True)
        typer.echo(f"{marca} {passo}")
    typer.secho(
        "  Dica: a chave é secreta — o openia a guarda só na sua máquina, "
        "fora do controle de versão.",
        fg=typer.colors.BRIGHT_BLACK,
    )
    typer.echo()


def _key_add_flow() -> None:
    """Pede nome + chave e salva. No primeiro cadastro, mostra como obter a chave."""
    if not config.list_keys():
        _explain_how_to_get_key()
    nome = typer.prompt(typer.style("✏️  Nome para esta chave (ex.: pessoal)",
                                     fg=typer.colors.CYAN))
    chave = typer.prompt(typer.style("🔑 Cole a chave do OpenRouter", fg=typer.colors.CYAN),
                         hide_input=True)
    try:
        warning = config.add_key(nome, chave)
    except ValueError as exc:
        ui.error(str(exc))
        return
    ui.success(f"chave '{nome}' salva e ativada.")
    if warning:
        ui.warn(warning)
    # Formato OK não garante que a chave autentica; testa de verdade na rede.
    _testar_chave(chave)


def _testar_chave(chave: str) -> None:
    """Valida a chave contra o OpenRouter e relata o resultado.

    Não bloqueia: se a chave não autenticar (ou houver problema de rede) apenas
    avisa, para o usuário poder ajustar antes de tentar rodar uma interface e ver
    a CLI falhar lá dentro com um erro críptico.
    """
    ui.info("testando a chave no OpenRouter…", emoji="🌐")
    resultado = usage.check_api_key(chave)
    if resultado.ok:
        ui.success(resultado.reason)
    else:
        ui.warn(resultado.reason)


def _key_rename_flow() -> None:
    """Escolhe uma chave e a renomeia."""
    chaves = config.list_keys()
    idx = _pick_from("Renomear qual chave?", [nk.name for nk in chaves])
    if idx is None:
        return
    antigo = chaves[idx].name
    novo = typer.prompt(typer.style(f"novo nome para '{antigo}'", fg=typer.colors.CYAN))
    try:
        config.rename_key(antigo, novo)
    except ValueError as exc:
        ui.error(str(exc))
        return
    ui.success(f"'{antigo}' renomeada para '{novo}'.")


def _key_pick_and(acao: Callable[[str], None]) -> None:
    """Escolhe uma chave por nome e executa ``acao(nome)``, tratando erro."""
    chaves = config.list_keys()
    idx = _pick_from("Escolha a chave:", [nk.name for nk in chaves])
    if idx is None:
        return
    try:
        acao(chaves[idx].name)
    except ValueError as exc:
        ui.error(str(exc))


def _menu_show_usage() -> None:
    """Mostra uso/saldo da chave ativa, consultando o OpenRouter."""
    api_key = config.load_api_key()
    if not api_key:
        ui.warn("configure uma chave primeiro para ver o uso.")
        return
    try:
        u = usage.fetch_usage(api_key)
    except usage.UsageError as exc:
        ui.error(str(exc))
        return
    ui.section("Uso no OpenRouter (chave ativa)")
    ui.info(usage.format_line(u), emoji="📊")


def _menu_statusline() -> None:
    """Ativa a statusline de custo no Claude Code, mostrando o que muda antes.

    O `/cost` nativo do Claude Code usa preços da Anthropic, imprecisos via
    OpenRouter. Esta statusline chama `openia statusline`, que mostra uso/saldo
    reais do OpenRouter. Mexe no ~/.claude/settings.json (global), então exibe
    o que será gravado e pede confirmação, preservando o resto do arquivo.
    """
    from pathlib import Path

    settings_path = Path.home() / ".claude" / "settings.json"
    comando = f"{sys.executable} -m openia statusline"
    nova_entrada = {"type": "command", "command": comando}

    atual: dict = {}
    if settings_path.exists():
        try:
            atual = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            ui.error(f"não consegui ler {settings_path}; verifique o arquivo à mão.")
            return

    if atual.get("statusLine") == nova_entrada:
        ui.info("a statusline já está configurada.", emoji="✅")
        return

    ui.section("Isto será gravado em ~/.claude/settings.json")
    ui.warn("é a configuração GLOBAL do seu Claude Code, fora deste projeto.")
    typer.echo('  "statusLine": ' + json.dumps(nova_entrada, indent=2))
    if atual.get("statusLine"):
        typer.echo("  (substituirá a statusLine atual)")

    if not typer.confirm("  aplicar essa mudança?", default=False):
        ui.info("nada foi alterado.", emoji="")
        return

    atual["statusLine"] = nova_entrada
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(atual, indent=2), encoding="utf-8")
    ui.success("statusline ativada. Abra o Claude Code para ver o uso na barra.")


def _run_interface_flow(iface: AIInterface) -> None:
    """Instala (se preciso), escolhe modo/modelo e roda a interface escolhida.

    Qualquer 'voltar' (0) num sub-passo cancela o fluxo e retorna ao menu, em
    vez de avançar — sinalizado por ``_Cancelado``.
    """
    try:
        _run_interface_flow_inner(iface)
    except _Cancelado:
        ui.info("voltando ao menu.", emoji="↩️")


def _run_interface_flow_inner(iface: AIInterface) -> None:
    if not runner.is_installed(iface):
        ui.warn(f"{iface.name} ainda não está instalada.")
        if not typer.confirm("  instalar agora?", default=True):
            raise _Cancelado
        try:
            _install_with_consent(iface)
        except typer.Exit:
            raise _Cancelado
        _show_setup_hint(iface)

    use_provider = _decide_mode(iface, subscription=False, provider=False)

    api_key = None
    model_id = None
    if use_provider:
        if config.load_api_key() is None:
            ui.warn("você ainda não cadastrou nenhuma chave do OpenRouter.")
            _key_add_flow()
            if config.load_api_key() is None:
                raise _Cancelado
        api_key = config.load_api_key()
        # Confere que a chave realmente autentica antes de entregar à CLI: uma
        # chave "ativa" porém revogada/sem saldo só falharia lá dentro, com erro
        # críptico. Em falha de rede deixamos seguir (pode ser falso-negativo).
        check = usage.check_api_key(api_key)
        if not check.ok:
            ui.warn(f"a chave ativa não passou no teste: {check.reason}")
            if not typer.confirm("  tentar mesmo assim?", default=False):
                raise _Cancelado
        if typer.confirm("  escolher o modelo agora (empresa → modelo)?", default=True):
            model_id = _apply_or_explain_model(iface, _choose_model(iface))
    else:
        ui.success(f"usando a autenticação própria do {iface.name} (sem OpenRouter).")

    # Agentes de código precisam rodar na raiz do projeto certo (ver _choose_workdir).
    cwd = _choose_workdir(iface) if iface.is_code_agent else None

    ui.banner(f"{iface.emoji}  iniciando {iface.name}")
    try:
        runner.run(iface, api_key, model_id=model_id, use_provider=use_provider, cwd=cwd)
    except runner.ToolingError as exc:
        ui.error(str(exc))
        return
    ui.info("a sessão terminou — voltando ao menu.", emoji="↩️")


def force_utf8_output() -> None:
    """Garante saída UTF-8 no terminal (sobretudo no Windows).

    Sem isto, o console do Windows usa cp1252 por padrão e quebra com
    ``UnicodeEncodeError`` ao imprimir caracteres como ``✓``, emojis ou um
    caminho de projeto com acentos. Idempotente e seguro em qualquer plataforma.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass  # stream não regravável (ex.: redirecionado); ignora


def entrypoint() -> None:
    """Ponto de entrada para ``python -m openia`` e para o script de console."""
    force_utf8_output()
    app()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())  # type: ignore[func-returns-value]
