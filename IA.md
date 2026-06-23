# IA.md — contexto operacional do orctl

> Registro vivo de decisões, estado e próximos passos. Atualize ao mudar o projeto.

## O que é

`orctl` é um launcher em Python para CLIs de IA de terminal compatíveis com
OpenRouter. O usuário escolhe a interface; o programa instala, configura a chave
e abre a ferramenta. A escolha de modelo é feita dentro de cada CLI.

Stack (caso 3.4 do padrão — scripts/automação): Python + Typer + pytest.

## Arquitetura

Responsabilidades separadas em camadas finas:

- `orctl/interfaces/base.py` — contrato `AIInterface` (descrição declarativa de uma CLI).
- `orctl/interfaces/registry.py` — registro das interfaces suportadas. **Único lugar a editar para adicionar ferramenta** (Open/Closed).
- `orctl/config.py` — chave do OpenRouter e montagem do ambiente de execução.
- `orctl/runner.py` — instalar / detectar / executar (isola pip, npm e SO); aplica o modelo por flag/env quando a interface suporta.
- `orctl/models.py` — catálogo de modelos do OpenRouter: busca `/api/v1/models`, agrupa por empresa, com cache local de 24h e fallback para cache em caso de falha de rede.
- `orctl/cli.py` — interface do usuário (Typer): `list`, `key`, `install`, `run` e menu.
- `start_app.py` — ponto de entrada único (contrato GUIA-START-APP-SCRIPT): instala dependências e abre o menu. Adaptado para CLI (sem porta/restart/navegador, com justificativa no cabeçalho).

## Decisões tomadas

- **Instalação direto no sistema** (pip/npm global), sem venv/pipx — escolha do usuário. Trade-off: simples, mas sem isolamento; risco de conflito entre pacotes.
- **Chave em `.env` local** (`orctl/.env`, chmod 600), no `.gitignore`. Repasse por env var ao processo filho. Env var exportada tem prioridade sobre o arquivo.
- **Escolha de modelo empresa → modelo** no orctl, antes de iniciar (fonte: API do OpenRouter ao vivo + cache). A "versão" vem embutida no nome do modelo (ex.: `claude-opus-4.1`), não é um terceiro nível na API.
- **Aplicação do modelo é honesta por ferramenta:** quem aceita o id do OpenRouter por flag (opencode `--model`, cline `-m`) recebe automaticamente; quem usa formato próprio ou só escolhe na UI (orchat, aichat, llm, openclaw) recebe instrução de qual modelo usar. Controlado por `model_arg`/`model_env`/`model_prefix`/`model_select_in_app` no contrato.
- OpenRouter é OpenAI-compatível: ferramentas genéricas recebem `OPENAI_API_KEY` + base_url apontando para `https://openrouter.ai/api/v1`.
- **Ecossistemas suportados:** PYTHON (pip), NODE (npm) e SCRIPT (instalador oficial via `curl | bash`). Instalação via SCRIPT exige consentimento explícito (`allow_script`), porque executa código remoto.
- **setup_hint:** ferramentas que não aceitam a chave só por env var (ex.: openclaw) trazem um passo de config próprio, que o orctl **mostra** mas não executa (não assume entrada interativa).
- **base_url por interface + clear_env:** a base_url deixou de ser fixa. O Claude Code usa `ANTHROPIC_BASE_URL=https://openrouter.ai/api` (sem `/v1`), chave em `ANTHROPIC_AUTH_TOKEN` e `ANTHROPIC_API_KEY` esvaziada via `clear_env` (evita o conflito que causa "model not found").
- **Interfaces atuais (7):** chat — orchat, aichat, llm; agentes de código — cline (npm), opencode (script), openclaw (npm + onboard), claudecode (npm, protocolo Anthropic).

## Testes

`python3 -m pytest -q` → 12 testes passando (validação/gravação de chave com
permissão 600, prioridade de env var, montagem de ambiente, registro de interfaces).

## Verificação manual feita

- `key set` grava `orctl/.env` com `-rw-------` (600). ✓
- `key show` exibe a chave mascarada. ✓
- `git check-ignore orctl/.env` confirma que o segredo está ignorado. ✓
- `list` mostra as 3 interfaces com status de instalação. ✓
- `python start_app.py --no-install list` e `key show` repassam ao orctl. ✓
- `start_app.py` abre o menu interativo e sai limpo (exit 0). ✓
- Detecção de dependência ausente (`missing_deps`) dispara o `pip install`. ✓
- `run opencode --version` ponta a ponta: orctl resolve a interface, monta o ambiente com a chave e invoca o binário real (respondeu `1.17.9`, exit 0). ✓ Fecha o risco antes aberto no caminho de execução.
- Catálogo ao vivo: `load_models()` trouxe 338 modelos / 55 empresas do OpenRouter e gravou cache. ✓
- Fluxo empresa→modelo: escolha de anthropic → modelo monta `opencode --model <id>` com base_url do OpenRouter no env; para orchat (select_in_app) instrui em vez de passar flag. ✓
- Claude Code: `build_run_env` monta `ANTHROPIC_BASE_URL=https://openrouter.ai/api` (sem /v1), token em `ANTHROPIC_AUTH_TOKEN` e esvazia `ANTHROPIC_API_KEY` mesmo quando ela já existe no ambiente. ✓

## Riscos e limites conhecidos

- O caminho `run` foi validado de ponta a ponta com `opencode` (já instalado na
  máquina). A **instalação** de cada ferramenta ainda não foi exercitada uma a
  uma — depende de rede e dos pacotes existirem com o nome esperado no
  PyPI/npm/instalador oficial.
- `openclaw` precisa do passo `onboard` para gravar a chave; o orctl mostra o
  comando, mas não confere se o usuário rodou.
- Sem isolamento de instalação, atualizar uma CLI pode afetar dependências do sistema.

## Ideias para quem quiser contribuir

- Adicionar mais interfaces ao registro (ex.: agentes de código como Codex CLI,
  Cline, Kilo Code) — basta uma nova `AIInterface`.
- Suporte opcional a isolamento via pipx/venv como alternativa ao install global.
- Listar/escolher modelos do OpenRouter direto no menu para as CLIs que aceitam
  modelo por flag.
