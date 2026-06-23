# Testes com IA

Repositório de testes e referências sobre as melhores plataformas de IA para uso no terminal.

---

## orctl — launcher de CLIs de IA com OpenRouter

`orctl` é um pequeno programa em Python que deixa você escolher, instalar e
abrir uma CLI de IA de terminal já configurada com sua chave do OpenRouter.
A escolha do **modelo** acontece dentro de cada ferramenta; o `orctl` cuida de
instalar, guardar a chave com segurança e iniciar a interface certa.

### Como rodar

Forma mais simples (instala dependências e abre o menu para escolher tudo):

```bash
python start_app.py
```

- `python start_app.py key` — configura sua chave do OpenRouter (gere em https://openrouter.ai/keys)
- `python start_app.py list` — lista as interfaces suportadas
- `python start_app.py --no-install` — pula a instalação de dependências

> Não é um servidor web: por ser uma CLI interativa, o `start_app.py` não tem
> `restart`/porta/navegador; o equivalente a "abrir o app" é abrir o menu.

### Uso direto (opcional)

Se preferir, dá pra chamar o módulo direto (requer `pip install typer`):

```bash
python3 -m orctl                # menu interativo
python3 -m orctl key set        # pede a chave sem mostrar na tela
python3 -m orctl run orchat     # instala (se preciso) e abre a interface
```

> Instalando o pacote (`pip install -e .`) o comando vira apenas `orctl`.

### Interfaces suportadas

| Chave | Ferramenta | Para quê |
|---|---|---|
| `orchat` | [OrChat](https://github.com/oop7/OrChat) | Chat rico: streaming, tokens, resumo |
| `aichat` | [aichat](https://github.com/sigoden/aichat) | Chat/REPL leve, OpenAI-compatível |
| `llm`    | [llm](https://github.com/simonw/llm) | CLI extensível com plugins e logs |

Adicionar uma nova interface é só registrar uma `AIInterface` em
[orctl/interfaces/registry.py](orctl/interfaces/registry.py) — o núcleo não muda.

### Segurança da chave

- A chave **nunca** entra no código nem em arquivo versionado.
- É gravada em `orctl/.env` com permissão `600` e está no `.gitignore`.
- Na execução, é repassada à CLI por variável de ambiente (não por argumento).
- Uma variável `OPENROUTER_API_KEY` já exportada tem prioridade sobre o arquivo.

### Testes

```bash
pip install pytest
python3 -m pytest -q
```

---

## Melhores plataformas de IA para o terminal

Ferramentas que rodam como agentes de código diretamente no terminal (CLI), com capacidade de ler, editar e criar arquivos, executar comandos e interagir com o projeto de forma autônoma.

---

### 1. Claude Code — Anthropic

**Site:** https://claude.ai/code

A ferramenta oficial da Anthropic para desenvolvimento via terminal. Atua como um agente completo com acesso ao filesystem, Git, e execução de comandos.

- Modelos: Claude Opus 4, Sonnet 4.6, Haiku 4.5
- Context window de até 200k tokens
- Suporte a agentes paralelos e MCP (Model Context Protocol)
- Extensões para VS Code, Cursor e JetBrains
- Plano gratuito com limites via claude.ai
- **Open source:** Não

```bash
npm install -g @anthropic-ai/claude-code
claude
```

---

### 2. Gemini CLI — Google

**Site:** https://github.com/google-gemini/gemini-cli

CLI open source do Google com contexto de 1 milhão de tokens e integração com Google Search.

- Modelo: Gemini 2.5 Pro/Flash
- 60 req/min e 1000 req/dia gratuitamente (conta pessoal Google)
- Integração com GitHub Actions
- Suporte a MCP
- **Open source:** Sim

```bash
npm install -g @google/gemini-cli
gemini
```

---

### 3. Aider — Open Source

**Site:** https://aider.chat

Um dos pioneiros em pair programming no terminal. Foco total em Git — faz commits automáticos com mensagens inteligentes a cada alteração.

- Suporta Claude, GPT-4, DeepSeek, Gemini e qualquer LLM compatível com OpenAI
- Mapeia automaticamente o codebase inteiro
- Suporte a 50+ linguagens
- **Open source:** Sim (MIT)

```bash
pip install aider-install
aider --model claude-sonnet-4-5
```

---

### 4. OpenCode — Open Source

**Site:** https://opencode.ai

Terminal-first (TUI) com suporte a 75+ provedores de LLM, incluindo modelos locais via Ollama. Sem vendor lock-in.

- Modos Plan e Build para revisar antes de modificar
- LSP, MCP e comandos customizados
- Suporta OpenRouter, Anthropic, OpenAI, Gemini, Bedrock, Ollama
- **Open source:** Sim

```bash
npm install -g opencode-ai
opencode
```

---

### 5. Codex CLI — OpenAI

**Site:** https://github.com/openai/codex

CLI open source da OpenAI escrito em Rust. Integrado ao ecossistema ChatGPT com suporte a skills e MCP.

- Modelo recomendado: GPT-4o / o3
- Parallel tool calls via MCP
- **Open source:** Sim (MIT)
- Requer conta OpenAI (pago)

```bash
npm install -g @openai/codex
codex
```

---

### 6. Amazon Q Developer CLI — AWS

**Site:** https://docs.aws.amazon.com/amazonq

CLI da Amazon com foco em desenvolvedores AWS. Tem tier gratuito e integração profunda com o ecossistema da AWS.

- Modelo: Claude 3.7 Sonnet (por baixo)
- Autocompletar de comandos shell
- Comando `q chat --resume` para persistir conversas
- **Open source:** Não
- **Plano gratuito:** Sim

```bash
# Instalar via AWS CLI ou pacote direto
q chat
```

---

### 7. Goose — Block / Linux Foundation

**Site:** https://block.github.io/goose

Agente open source de propósito geral (não só código), desenvolvido pelo Block e agora sob a Linux Foundation. Construído em Rust.

- Suporta 25+ provedores LLM
- 70+ extensões via MCP
- Desktop app + CLI + API
- Backing de AWS, Anthropic, Google, Microsoft, OpenAI
- **Open source:** Sim (Apache 2.0)

```bash
# via script de instalação oficial
curl -fsSL https://github.com/block/goose/releases/latest/download/install.sh | bash
goose
```

---

## Comparativo rápido

| Ferramenta | Open Source | Gratuito | Destaque |
|---|---|---|---|
| Claude Code | Não | Sim (com limites) | Melhor agente geral, integração completa |
| Gemini CLI | Sim | Sim (generoso) | 1M tokens, Google Search grounding |
| Aider | Sim | Sim | Git-first, commits automáticos |
| OpenCode | Sim | Sim | 75+ providers, sem lock-in |
| Codex CLI | Sim | Não | Ecossistema OpenAI |
| Amazon Q CLI | Não | Sim | Foco AWS |
| Goose | Sim | Sim | Propósito geral, 70+ extensões MCP |

---

## Como escolher

- **Quer o melhor agente sem se preocupar com custo?** → Claude Code
- **Quer gratuito e open source?** → Gemini CLI ou Aider
- **Quer usar múltiplos providers sem lock-in?** → OpenCode
- **Trabalha com AWS?** → Amazon Q CLI
- **Quer além de código (pesquisa, automação)?** → Goose
