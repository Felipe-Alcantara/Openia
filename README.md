# 🤖 openia

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Typer](https://img.shields.io/badge/CLI-Typer-009688?style=for-the-badge&logo=typer&logoColor=white)
![OpenRouter](https://img.shields.io/badge/OpenRouter-API-6E56CF?style=for-the-badge)
![Tests](https://img.shields.io/badge/Tests-46%20passing-2ea44f?style=for-the-badge&logo=pytest&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

**Escolha, instale e abra uma CLI de IA de terminal já configurada com sua chave do OpenRouter — tudo por um menu interativo.**

[🚀 Como Usar](#-como-usar) • [🧩 Interfaces](#-interfaces-suportadas) • [🔐 Segurança da Chave](#-segurança-da-chave) • [📚 Referência de CLIs de IA](#-referência-melhores-clis-de-ia-para-o-terminal)

</div>

---

`openia` é um pequeno launcher em Python que tira o atrito de usar CLIs de IA no
terminal: você escolhe a ferramenta num **menu interativo**, e o openia instala,
guarda sua chave do OpenRouter com segurança e abre a interface certa já
configurada. A escolha do **modelo** acontece em dois passos (empresa → modelo),
com a lista vinda da API do OpenRouter ao vivo.

## 📋 Índice

- [📋 Sobre o Projeto](#-sobre-o-projeto)
- [📁 Estrutura do Projeto](#-estrutura-do-projeto)
- [🚀 Como Usar](#-como-usar)
- [🧬 Escolha de Modelo (empresa → modelo)](#-escolha-de-modelo-empresa--modelo)
- [🧩 Interfaces Suportadas](#-interfaces-suportadas)
- [🔑 Várias Chaves Nomeadas](#-várias-chaves-nomeadas)
- [🔐 Segurança da Chave](#-segurança-da-chave)
- [🧾 Custo no Claude Code](#-custo-no-claude-code)
- [💻 Multiplataforma](#-multiplataforma)
- [🧪 Testes](#-testes)
- [📚 Referência: Melhores CLIs de IA para o Terminal](#-referência-melhores-clis-de-ia-para-o-terminal)
- [⚠️ Limitações](#️-limitações)
- [📝 Licença](#-licença)
- [👤 Autor](#-autor)
- [🤝 Contribuições](#-contribuições)

---

## 📋 Sobre o Projeto

CLIs de IA de terminal são poderosas, mas cada uma instala de um jeito, espera a
chave em uma variável diferente e configura o provedor à sua maneira. O `openia`
padroniza essa porta de entrada: um único comando abre um **menu** onde você
**escolhe a interface**, **configura a chave do OpenRouter** e **inicia** a
ferramenta já apontada para o provedor certo.

- **🎯 Menu primeiro** — nada de decorar flags; tudo se resolve no menu.
- **🔐 Chave segura** — guardada localmente (gitignored, `600` no Unix), nunca no código.
- **🧬 Modelo por empresa** — escolha Anthropic/OpenAI/Google… e depois o modelo, com preço por linha.
- **🧩 Aberto para extensão** — adicionar uma CLI nova é registrar uma `AIInterface`; o núcleo não muda.

---

## 📁 Estrutura do Projeto

```
Openia/
│
├── 📁 openia/                  # Pacote principal (camadas finas e separadas)
│   ├── 📁 interfaces/
│   │   ├── base.py             # Contrato AIInterface (descrição de uma CLI)
│   │   └── registry.py         # Registro das CLIs suportadas (único ponto a editar)
│   ├── cli.py                  # Comandos Typer (list/key/install/run) e o menu
│   ├── config.py               # Chaves do OpenRouter + montagem do ambiente
│   ├── runner.py               # Instalar / detectar / executar (isola pip, npm, SO)
│   ├── models.py               # Catálogo de modelos do OpenRouter (com cache 24h)
│   ├── ui.py                   # Apresentação do menu (molduras, cores, prompts)
│   └── usage.py                # Uso/saldo no OpenRouter e validação de chave
│
├── 📁 tests/                   # Testes (pytest) — 46 passando
├── 📁 scripts/                 # Instaladores do comando `openia` por shell
├── start_app.py                # Porta de entrada única: menu interativo
├── IA.md                       # Contexto operacional (decisões, bugs, testes)
├── README.md                   # Este arquivo
└── LICENSE
```

---

## 🚀 Como Usar

### Opção 1: Forma mais fácil (Recomendado!) 🌟

Um comando só — ele instala o que precisa e abre o **menu interativo**:

```bash
python start_app.py
```

No menu você escolhe tudo sem decorar comando — as quatro ações do contrato de
porta de entrada estão lá: **Iniciar/Rodar** uma interface, **Instalar/Setup**
de uma CLI, **Configurar** a chave do OpenRouter (gere em
https://openrouter.ai/keys) e **Status/Sair**. Quando a sessão termina, você
volta ao menu. Para sair, escolha `0`.

```
╭──────────────────────────────────────────────────────────────╮
│                            openia                             │
│          interfaces de IA no terminal · OpenRouter           │
╰──────────────────────────────────────────────────────────────╯

 Escolha uma interface
 ──────────────────────────────────────────────────────────────
  [1] 💬 OrChat · não instalada
  ...
  [7] 🧠 Claude Code · instalada

 Instalar e configurar
  [8]  📦 Instalar / Setup de uma interface
  [9]  🔑 Chaves do OpenRouter · ativa: pessoal

 Status e uso
  [10] 🩺 Status do openia
  [11] 📊 Ver meu uso/saldo no OpenRouter
  [12] 🧾 Statusline de custo no Claude Code
  [0]  sair
```

> Não é um servidor web: por ser uma CLI interativa, o `start_app.py` não tem
> `restart`/porta/navegador; o equivalente a "abrir o app" é abrir o menu.

### Opção 2: Para desenvolvedores

Dá pra chamar o módulo direto (requer `pip install typer`):

```bash
python3 -m openia                # menu interativo
python3 -m openia key set        # pede a chave sem mostrar na tela
python3 -m openia run orchat     # instala (se preciso) e abre a interface
```

> Instalando o pacote (`pip install -e .`) o comando vira apenas `openia`.

---

## 🧬 Escolha de Modelo (empresa → modelo)

Antes de iniciar qualquer interface, o openia deixa você escolher o modelo em
dois passos: primeiro a **empresa** (Anthropic, OpenAI, Google, …), depois o
**modelo** (a versão já vem no nome, ex.: `claude-opus-4.1`). A lista vem da API
do OpenRouter ao vivo, com cache local de 24h.

Os modelos de cada empresa são listados **do mais caro ao mais barato** (preço
de saída por milhão de tokens, mostrado em cada linha) — assim os modelos mais
capazes tendem a ficar no topo e os `free` no fim.

Como cada CLI aceita o modelo de um jeito, o openia é honesto sobre isso:

- **opencode** e **cline** aceitam o id do OpenRouter por flag — o openia aplica sozinho.
- **orchat**, **aichat**, **llm** e **openclaw** escolhem o modelo na própria
  interface (formato próprio) — o openia mostra qual modelo usar lá dentro.

Tudo isso acontece dentro do menu. Quem preferir linha de comando ainda pode usar
`run <interface> -m <empresa/modelo>` ou `--no-model`, mas não é necessário.

---

## 🧩 Interfaces Suportadas

**Chat:**

| Chave | Ferramenta | Para quê |
|---|---|---|
| `orchat` | [OrChat](https://github.com/oop7/OrChat) | Chat rico: streaming, tokens, resumo |
| `aichat` | [aichat](https://github.com/sigoden/aichat) | Chat/REPL leve, OpenAI-compatível |
| `llm`    | [llm](https://github.com/simonw/llm) | CLI extensível com plugins e logs |

**Agentes de código** (leem/editam arquivos e rodam comandos):

| Chave | Ferramenta | Instalação | Observação |
|---|---|---|---|
| `cline`    | [Cline](https://github.com/cline/cline) | npm | OpenRouter nativo |
| `opencode` | [opencode](https://opencode.ai) | script oficial (`curl \| bash`, pede confirmação) | OpenRouter via base_url |
| `openclaw` | [OpenClaw](https://github.com/openclaw/openclaw) | npm | 1ª vez: rodar `openclaw onboard` (o openia mostra o comando) |
| `claudecode` | [Claude Code](https://docs.claude.com/claude-code) | npm | Fala o protocolo Anthropic; otimizado p/ modelos Anthropic |

> **Claude Code — dois modos:** ao iniciar, o openia pergunta como autenticar:
>
> - **OpenRouter** — usa as variáveis da Anthropic (não o padrão OpenAI):
>   `ANTHROPIC_BASE_URL=https://openrouter.ai/api` (sem `/v1`),
>   `ANTHROPIC_AUTH_TOKEN` com a chave do OpenRouter e `ANTHROPIC_API_KEY` vazia.
>   O openia monta isso sozinho. Funciona melhor com modelos Anthropic.
> - **Assinatura** — roda o Claude Code com o login da sua conta Anthropic
>   (Pro/Max), sem OpenRouter. O openia remove as variáveis `ANTHROPIC_*` do
>   ambiente para não atrapalhar o login.
>
> Direto: `run claudecode --subscription` ou `run claudecode --provider`.
> Se você alterna entre os dois, pode precisar de `/login` ou `/logout` dentro
> do Claude Code; confirme com `/status`.

Adicionar uma nova interface é só registrar uma `AIInterface` em
[openia/interfaces/registry.py](openia/interfaces/registry.py) — o núcleo não muda.

---

## 🔑 Várias Chaves Nomeadas

Você pode cadastrar quantas chaves quiser, cada uma com um nome (ex.: `pessoal`,
`trabalho`), e escolher qual fica **ativa**. Tudo pelo menu (opção *Chaves do
OpenRouter*): adicionar, trocar a ativa, renomear e remover. A opção *Ver meu
uso/saldo* mostra quanto você já gastou e quanto resta na chave ativa.

---

## 🔐 Segurança da Chave

- As chaves **nunca** entram no código nem em arquivo versionado.
- São gravadas em `openia/keys.json` (no `.gitignore`). Um `.env` antigo de chave
  única é migrado automaticamente.
- No Linux/macOS o arquivo recebe permissão `600` (só o dono lê/escreve). No
  Windows as permissões POSIX não se aplicam, então o openia avisa — mantenha a
  pasta privada.
- Na execução, a chave ativa é repassada à CLI por variável de ambiente (não por
  argumento). Uma `OPENROUTER_API_KEY` já exportada tem prioridade.

---

## 🧾 Custo no Claude Code

O `/cost` nativo do Claude Code é impreciso via OpenRouter (usa preços da
Anthropic). Pelo menu, a opção *Statusline de custo no Claude Code* configura uma
statusline que mostra uso/saldo reais do OpenRouter na barra de status. Ela mexe
no `~/.claude/settings.json` (global), então o openia mostra exatamente o que será
gravado e pede confirmação antes, preservando o resto do arquivo.

---

## 💻 Multiplataforma

Funciona em Linux, macOS e Windows: o launcher usa `sys.executable` e só
biblioteca padrão; o `npm` vira `npm.cmd` no Windows; instaladores via script
usam `curl | sh` no Unix e PowerShell (`irm | iex`) no Windows. Quando um
pré-requisito falta (npm, curl, PowerShell), a mensagem diz o que instalar.

---

## 🧪 Testes

```bash
pip install pytest
python3 -m pytest -q
```

Cobrem gravação/validação de chave e permissão por SO, prioridade de env var,
montagem de ambiente provider/assinatura, catálogo de modelos e ordenação por
preço, registro de interfaces, comandos de instalação por SO e o gate de
consentimento de script. **46 testes passando.**

---

## 📚 Referência: Melhores CLIs de IA para o Terminal

Além do launcher, este repositório mantém uma referência das principais CLIs de
IA que rodam como agentes de código no terminal — capazes de ler, editar e criar
arquivos, executar comandos e interagir com o projeto de forma autônoma.

### 1. Claude Code — Anthropic

**Site:** https://claude.ai/code

Ferramenta oficial da Anthropic para desenvolvimento via terminal. Atua como um
agente completo com acesso ao filesystem, Git e execução de comandos.

- Modelos: Claude Opus 4, Sonnet 4.6, Haiku 4.5
- Context window de até 200k tokens
- Suporte a agentes paralelos e MCP (Model Context Protocol)
- Extensões para VS Code, Cursor e JetBrains
- **Open source:** Não

```bash
npm install -g @anthropic-ai/claude-code
claude
```

### 2. Gemini CLI — Google

**Site:** https://github.com/google-gemini/gemini-cli

CLI open source do Google com contexto de 1 milhão de tokens e integração com
Google Search.

- Modelo: Gemini 2.5 Pro/Flash
- 60 req/min e 1000 req/dia gratuitamente (conta pessoal Google)
- Integração com GitHub Actions e suporte a MCP
- **Open source:** Sim

```bash
npm install -g @google/gemini-cli
gemini
```

### 3. Aider — Open Source

**Site:** https://aider.chat

Um dos pioneiros em pair programming no terminal. Foco total em Git — faz commits
automáticos com mensagens inteligentes a cada alteração.

- Suporta Claude, GPT-4, DeepSeek, Gemini e qualquer LLM compatível com OpenAI
- Mapeia automaticamente o codebase inteiro; suporte a 50+ linguagens
- **Open source:** Sim (MIT)

```bash
pip install aider-install
aider --model claude-sonnet-4-5
```

### 4. OpenCode — Open Source

**Site:** https://opencode.ai

Terminal-first (TUI) com suporte a 75+ provedores de LLM, incluindo modelos
locais via Ollama. Sem vendor lock-in.

- Modos Plan e Build para revisar antes de modificar
- LSP, MCP e comandos customizados
- **Open source:** Sim

```bash
npm install -g opencode-ai
opencode
```

### 5. Codex CLI — OpenAI

**Site:** https://github.com/openai/codex

CLI open source da OpenAI escrito em Rust. Integrado ao ecossistema ChatGPT com
suporte a skills e MCP.

- Modelo recomendado: GPT-4o / o3
- Parallel tool calls via MCP
- **Open source:** Sim (MIT) — requer conta OpenAI (pago)

```bash
npm install -g @openai/codex
codex
```

### 6. Amazon Q Developer CLI — AWS

**Site:** https://docs.aws.amazon.com/amazonq

CLI da Amazon com foco em desenvolvedores AWS. Tem tier gratuito e integração
profunda com o ecossistema da AWS.

- Modelo: Claude 3.7 Sonnet (por baixo)
- Autocompletar de comandos shell; `q chat --resume` persiste conversas
- **Open source:** Não — **Plano gratuito:** Sim

```bash
# Instalar via AWS CLI ou pacote direto
q chat
```

### 7. Goose — Block / Linux Foundation

**Site:** https://block.github.io/goose

Agente open source de propósito geral (não só código), desenvolvido pelo Block e
agora sob a Linux Foundation. Construído em Rust.

- Suporta 25+ provedores LLM e 70+ extensões via MCP
- Desktop app + CLI + API
- **Open source:** Sim (Apache 2.0)

```bash
# via script de instalação oficial
curl -fsSL https://github.com/block/goose/releases/latest/download/install.sh | bash
goose
```

### Comparativo rápido

| Ferramenta | Open Source | Gratuito | Destaque |
|---|---|---|---|
| Claude Code | Não | Sim (com limites) | Melhor agente geral, integração completa |
| Gemini CLI | Sim | Sim (generoso) | 1M tokens, Google Search grounding |
| Aider | Sim | Sim | Git-first, commits automáticos |
| OpenCode | Sim | Sim | 75+ providers, sem lock-in |
| Codex CLI | Sim | Não | Ecossistema OpenAI |
| Amazon Q CLI | Não | Sim | Foco AWS |
| Goose | Sim | Sim | Propósito geral, 70+ extensões MCP |

### Como escolher

- **Quer o melhor agente sem se preocupar com custo?** → Claude Code
- **Quer gratuito e open source?** → Gemini CLI ou Aider
- **Quer usar múltiplos providers sem lock-in?** → OpenCode
- **Trabalha com AWS?** → Amazon Q CLI
- **Quer além de código (pesquisa, automação)?** → Goose

---

## ⚠️ Limitações

- **Instalação direto no sistema** (pip/npm global), sem venv/pipx — simples,
  mas sem isolamento; atualizar uma CLI pode afetar dependências do sistema.
- **`openclaw`** precisa do passo `onboard` para gravar a chave; o openia mostra
  o comando, mas não confere se você o rodou.
- **Preço como proxy de qualidade** é imperfeito: um modelo novo e bom pode ser
  barato e cair no fim da lista. É um critério prático, não um ranking de capacidade.

---

## 📝 Licença

Este projeto está sob a licença MIT — veja o arquivo [LICENSE](LICENSE).

## 👤 Autor

**Felipe Martin**
- GitHub: [@Felipe-Alcantara](https://github.com/Felipe-Alcantara)
- Repositório: [Openia](https://github.com/Felipe-Alcantara/Openia)

## 🤝 Contribuições

Contribuições são bem-vindas! Sinta-se à vontade para:
- Reportar bugs
- Sugerir novas interfaces (basta uma nova `AIInterface` em [registry.py](openia/interfaces/registry.py))
- Melhorar a documentação

Ideias abertas à comunidade: suporte opcional a isolamento via pipx/venv,
listar/escolher modelos direto no menu para mais CLIs, e novos agentes de código
no registro.

---

⭐ Se este projeto foi útil, considere dar uma estrela no GitHub!
