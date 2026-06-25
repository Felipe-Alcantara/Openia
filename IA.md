# IA.md — contexto operacional do openia

> Registro vivo de decisões, estado e próximos passos. Atualize ao mudar o projeto.

## O que é

`openia` é um launcher em Python para CLIs de IA de terminal compatíveis com
OpenRouter. O usuário escolhe a interface; o programa instala, configura a chave
e abre a ferramenta. A escolha de modelo é feita dentro de cada CLI.

Stack (caso 3.4 do padrão — scripts/automação): Python + Typer + pytest.

## Arquitetura

Responsabilidades separadas em camadas finas:

- `openia/interfaces/base.py` — contrato `AIInterface` (descrição declarativa de uma CLI).
- `openia/interfaces/registry.py` — registro das interfaces suportadas. **Único lugar a editar para adicionar ferramenta** (Open/Closed).
- `openia/config.py` — chave do OpenRouter e montagem do ambiente de execução.
- `openia/runner.py` — instalar / detectar / executar (isola pip, npm e SO); aplica o modelo por flag/env quando a interface suporta.
- `openia/models.py` — catálogo de modelos do OpenRouter: busca `/api/v1/models`, agrupa por empresa, com cache local de 24h e fallback para cache em caso de falha de rede.
- `openia/ui.py` — apresentação do menu (molduras Unicode, cores, emojis, prompts). Isola a aparência da lógica do `cli.py`.
- `openia/usage.py` — consulta uso/saldo no OpenRouter (`/api/v1/credits`); usado no menu e na statusline.
- `openia/cli.py` — interface do usuário (Typer): `list`, `key`, `install`, `run` e menu.
- `start_app.py` — ponto de entrada único (contrato GUIA-START-APP-SCRIPT): instala dependências e abre o menu. Adaptado para CLI (sem porta/restart/navegador, com justificativa no cabeçalho).

## Decisões tomadas

- **Instalação direto no sistema** (pip/npm global), sem venv/pipx — escolha do usuário. Trade-off: simples, mas sem isolamento; risco de conflito entre pacotes.
- **Chaves em `keys.json` local** (`openia/keys.json`, chmod 600 no Unix), no `.gitignore`. Repasse por env var ao processo filho. Env var exportada tem prioridade sobre o arquivo. (Histórico: começou como `.env` de chave única, migrado para múltiplas chaves nomeadas.)
- **Escolha de modelo empresa → modelo** no openia, antes de iniciar (fonte: API do OpenRouter ao vivo + cache). A "versão" vem embutida no nome do modelo (ex.: `claude-opus-4.1`), não é um terceiro nível na API.
- **Ordenação por preço (saída) desc:** modelos de uma empresa são listados do mais caro ao mais barato, com o preço por milhão de tokens no rótulo; `free` (preço 0) vai para o fim. A API não expõe "qualidade", então preço é o proxy escolhido. Campo `completion_price` no `Model`.
- **Aplicação do modelo é honesta por ferramenta:** quem aceita o id do OpenRouter por flag (opencode `--model`, cline `-m`) recebe automaticamente; quem usa formato próprio ou só escolhe na UI (orchat, aichat, llm, openclaw) recebe instrução de qual modelo usar. Controlado por `model_arg`/`model_env`/`model_prefix`/`model_select_in_app` no contrato.
- OpenRouter é OpenAI-compatível: ferramentas genéricas recebem `OPENAI_API_KEY` + base_url apontando para `https://openrouter.ai/api/v1`.
- **Ecossistemas suportados:** PYTHON (pip), NODE (npm) e SCRIPT (instalador oficial via `curl | bash`). Instalação via SCRIPT exige consentimento explícito (`allow_script`), porque executa código remoto.
- **setup_hint:** ferramentas que não aceitam a chave só por env var (ex.: openclaw) trazem um passo de config próprio, que o openia **mostra** mas não executa (não assume entrada interativa).
- **base_url por interface + clear_env:** a base_url deixou de ser fixa. O Claude Code usa `ANTHROPIC_BASE_URL=https://openrouter.ai/api` (sem `/v1`), chave em `ANTHROPIC_AUTH_TOKEN` e `ANTHROPIC_API_KEY` esvaziada via `clear_env` (evita o conflito que causa "model not found").
- **Interfaces atuais (7):** chat — orchat, aichat, llm; agentes de código — cline (npm), opencode (script), openclaw (npm + onboard), claudecode (npm, protocolo Anthropic).
- **Claude Code com dois modos de autenticação:** `supports_subscription=True`. Modo provider injeta as vars do OpenRouter; modo assinatura roda `claude` removendo `env_keys`/`base_url_env`/`clear_env` do ambiente (`runner._env_without_provider`), para o login OAuth Pro/Max funcionar. Escolha por `--subscription`/`--provider` ou no menu.
- **Múltiplas chaves nomeadas em `keys.json`** (não mais `.env`): cada chave tem nome, uma fica ativa; gerência completa pelo menu (adicionar/ativar/renomear/remover). Migra automaticamente um `.env` antigo de chave única para a chave 'padrão'. `load_api_key()` devolve a ativa (env var ainda tem prioridade). Arquivo com 0600 no Unix, gitignored.
- **Uso/saldo e statusline:** opção no menu mostra uso real do OpenRouter (`/credits`). Comando oculto `openia statusline` imprime a linha de uso; outra opção do menu instala isso no `~/.claude/settings.json` do Claude Code (porque o `/cost` nativo é impreciso via OpenRouter), sempre mostrando o que muda e pedindo confirmação, preservando o resto do arquivo.
- **Nome do projeto:** `openia` = "open" (OpenRouter) + "ia". Renomeado de `orctl` (que era difícil de lembrar) a pedido do usuário.
- **Menu interativo é o caminho principal** (pedido do usuário: não querer usar flags). `python start_app.py` abre um menu em loop com banner, emojis e cores: escolher interface, configurar a chave, escolher modo (assinatura/OpenRouter) e modelo (empresa→modelo) — tudo pelo teclado. As flags do comando `run` continuam existindo para uso avançado, mas não são necessárias. Apresentação isolada em `ui.py`; emoji por interface no contrato (`emoji`).
- **Multiplataforma (Linux/macOS/Windows):** `npm` → `npm.cmd` no Windows; instalador SCRIPT usa `curl | sh` no Unix e PowerShell `irm | iex` no Windows (`runner._script_install_cmd`); `save_api_key` aplica chmod 600 só no Unix e devolve aviso no Windows (POSIX não se aplica). `start_app.py` já era stdlib + `sys.executable`.
- **[2026-06-24] Agentes de código rodam na raiz do projeto (cwd):** dois problemas tinham a mesma causa — `runner.run` lançava a ferramenta sem definir `cwd`, então ela herdava o diretório de onde o openia foi chamado. (1) o agente não abria já no repositório (era preciso indicar o caminho no prompt); (2) o Claude Code não puxava o histórico da extensão do VS Code, porque ele indexa sessões por caminho do projeto (`~/.claude/projects/<path>`), e rodar de outro cwd aponta para outra pasta de sessões. Correção: novo campo `is_code_agent` no contrato (marca cline/opencode/openclaw/claudecode); `runner.run` aceita `cwd` e o repassa ao `subprocess.run`; `cli.py._choose_workdir` pergunta/valida a pasta (default = cwd atual) antes de iniciar um agente, com aviso específico do histórico para o Claude Code; comando `run` ganhou `--dir/-C` para passar o caminho não-interativamente (`_resolve_workdir`). Chats puros (orchat/aichat/llm) não pedem pasta. Testes: `test_run_repassa_cwd_ao_subprocess` + `fake_run` agora aceita `cwd`; 47 passando.
- **[2026-06-24] Menu cobre as 4 ações obrigatórias do GUIA-START-APP-SCRIPT:** o `start_app.py` é um bootstrapper fino que abre o menu do `openia` (cli.py). O menu já tinha Iniciar/Rodar, Configurar (chaves) e Sair, mas faltavam **Instalar/Setup** e **Status** como ações de primeira classe (o contrato exige as quatro). Adicionados `_menu_install` (instala uma interface sem iniciá-la, reusando o gate de consentimento de script) e `_menu_status` (checa de verdade: dep do menu via `find_spec`, chave ativa, e cada interface instalada/não). Menu reorganizado em seções "Instalar e configurar" e "Status e uso"; numeração agora n+1..n+5. Sem teste novo (são camadas de apresentação que reusam funções já testadas); 46 testes seguem passando e o menu foi validado à mão renderizando as 12 opções.
- **[2026-06-24] Passada de aderência ao padrão (Felixo System Design):** README reescrito no DESIGN_SYSTEM_README (header com badges centralizados, índice, estrutura, seções obrigatórias, autor/licença/CTA), com foco no programa `openia` e a lista de CLIs de IA mantida como seção de referência. Corrigido drift doc↔código: `.gitignore` tinha uma linha mojibake duplicada (`Padr├úo …`) que não casava com nada — a linha 2 acentuada é a que realmente ignora a pasta; `start_app.py` mencionava `openia/.env` (storage migrou para `keys.json`) e tinha docstring centrada em flags (padrão é menu-first); contagem de testes no IA.md estava em 37 (agora 46). Sem mudança de comportamento; 46 testes seguem passando.

## Testes

`python3 -m pytest -q` → 46 testes passando (gravação/validação de chave e
permissão por SO, prioridade de env var, montagem de ambiente provider/assinatura,
catálogo de modelos e ordenação por preço, registro de interfaces, comandos de
instalação por SO, gate de consentimento de script).

## Verificação manual feita

- `key set` grava `openia/.env` com `-rw-------` (600). ✓
- `key show` exibe a chave mascarada. ✓
- `git check-ignore openia/.env` confirma que o segredo está ignorado. ✓
- `list` mostra as 3 interfaces com status de instalação. ✓
- `python start_app.py --no-install list` e `key show` repassam ao openia. ✓
- `start_app.py` abre o menu interativo e sai limpo (exit 0). ✓
- Detecção de dependência ausente (`missing_deps`) dispara o `pip install`. ✓
- `run opencode --version` ponta a ponta: openia resolve a interface, monta o ambiente com a chave e invoca o binário real (respondeu `1.17.9`, exit 0). ✓ Fecha o risco antes aberto no caminho de execução.
- Catálogo ao vivo: `load_models()` trouxe 338 modelos / 55 empresas do OpenRouter e gravou cache. ✓
- Fluxo empresa→modelo: escolha de anthropic → modelo monta `opencode --model <id>` com base_url do OpenRouter no env; para orchat (select_in_app) instrui em vez de passar flag. ✓
- Claude Code: `build_run_env` monta `ANTHROPIC_BASE_URL=https://openrouter.ai/api` (sem /v1), token em `ANTHROPIC_AUTH_TOKEN` e esvazia `ANTHROPIC_API_KEY` mesmo quando ela já existe no ambiente. ✓
- Modo assinatura: `run claudecode --subscription` monta o comando `claude` sem nenhuma var `ANTHROPIC_*`, mesmo com `ANTHROPIC_API_KEY` exportada no shell. ✓
- Multiplataforma: montagem de comando validada para Windows (PowerShell `irm|iex`, `npm.cmd`) e Unix (`curl|sh`, `npm`) via patch de `os.name`; 30 testes. ✓

## Bugs corrigidos

- **"0 nunca voltava":** ao escolher voltar (0) em sub-passos como "como autenticar", o `None` de `_pick_from` era tratado como escolha e o fluxo avançava. Agora `_decide_mode` levanta `_Cancelado` no voltar, capturado em `_run_interface_flow`, retornando ao menu. Testes em `tests/test_cli.py`.

## Riscos e limites conhecidos

- O caminho `run` foi validado de ponta a ponta com `opencode` (já instalado na
  máquina). A **instalação** de cada ferramenta ainda não foi exercitada uma a
  uma — depende de rede e dos pacotes existirem com o nome esperado no
  PyPI/npm/instalador oficial.
- `openclaw` precisa do passo `onboard` para gravar a chave; o openia mostra o
  comando, mas não confere se o usuário rodou.
- Sem isolamento de instalação, atualizar uma CLI pode afetar dependências do sistema.
- Cache de modelos gravado antes do campo `completion_price` carrega com preço 0 (ordenação fica neutra) até o cache expirar (24h) ou um `force_refresh`. Não quebra; só não ordena por preço enquanto durar o cache antigo.
- Preço como proxy de qualidade é imperfeito: um modelo novo e bom pode ser barato e cair na lista. É um critério prático, não um ranking de capacidade.

## Ideias para quem quiser contribuir

- Adicionar mais interfaces ao registro (ex.: agentes de código como Codex CLI,
  Cline, Kilo Code) — basta uma nova `AIInterface`.
- Suporte opcional a isolamento via pipx/venv como alternativa ao install global.
- Listar/escolher modelos do OpenRouter direto no menu para as CLIs que aceitam
  modelo por flag.
