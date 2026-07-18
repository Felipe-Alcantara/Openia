# CLAUDE.md — Instruções para o Claude Code neste repositório

> Carregado automaticamente pelo Claude Code sempre que ele abre neste projeto.
> Define o contrato de qualidade, convenções e memória operacional que o agente
> deve seguir **sem que o usuário precise pedir**.

---

## 1. Contrato de qualidade (sempre ativo)

Ao trabalhar neste repositório, siga o **Guia Mínimo de Qualidade** do Felixo
System Design. Os princípios obrigatórios:

1. **Entender antes de alterar** — leia a estrutura existente, identifique o
   padrão local e preserve a intenção do projeto.
2. **Manter responsabilidades separadas** — regra de negócio não se mistura com
   UI, acesso a dados ou integração externa.
3. **Preferir simplicidade verificável** — a solução mais simples que resolve o
   problema real. Sem camada extra sem justificativa concreta.
4. **Preservar contratos** — APIs, DTOs, modelos e formatos de resposta estáveis.
5. **Validar entradas e erros** — toda entrada externa validada; erros previsíveis
   e seguros.
6. **Proteger dados e segredos** — nunca registrar tokens, senhas ou dados
   sensíveis em repositório.
7. **Testar comportamento importante** — regras críticas, bugs corrigidos e
   contratos precisam de teste.
8. **Documentar estado relevante** — `IA.md` como linha do tempo (nunca apagar
   registros antigos; adicionar entrada datada).
9. **Preferir automação e ferramenta reutilizável** — antes de editar manualmente,
   procure scripts, comandos ou ferramentas existentes.
10. **Fazer mudança pequena e rastreável** — commits atômicos no formato
    `tipo: descricao` (`feat`/`fix`/`docs`/`refactor`/`chore`).
11. **Finalizar com critério de pronto** — código revisado, testes passando,
    documentação atualizada, riscos registrados.

> Fonte completa: `Padrão de qualidade - Felixo System Design/core/GUIA_MINIMO_QUALIDADE.md`

---

## 2. Memória operacional

Leia `IA.md` **antes de qualquer alteração** — ele contém:
- Decisões técnicas e arquiteturais (com datas e motivos)
- Bugs corrigidos e riscos conhecidos
- Estado atual dos testes (54 passando)
- Linha do tempo completa do projeto

Ao concluir uma mudança, **atualize o `IA.md`** com uma nova entrada datada
explicando o que mudou, por que e como foi validado. **Nunca apague ou reescreva**
entradas antigas — o `IA.md` é linha do tempo, não resumo.

---

## 3. Stack e convenções do projeto

- **Linguagem**: Python 3.10+
- **CLI framework**: Typer
- **Testes**: pytest (`python -m pytest -q`)
- **Pacote principal**: `openia/`
- **Contrato de interfaces**: `openia/interfaces/base.py` → `AIInterface`
- **Registro de interfaces**: `openia/interfaces/registry.py` (único lugar a
  editar para adicionar ferramenta — princípio Open/Closed)
- **Instalação**: direto no sistema (pip/npm global), sem venv
- **Versionamento**: direto no `main`; branch só para feature grande ou alto risco
- **Idioma do código e docs**: português

---

## 4. Estrutura de camadas

```
openia/
├── interfaces/          # Contrato (base.py) + Registro (registry.py)
├── cli.py               # Comandos Typer + menu interativo
├── config.py            # Chaves do OpenRouter + ambiente de execução
├── runner.py            # Instalar / detectar / executar (isola pip, npm, SO)
├── models.py            # Catálogo de modelos do OpenRouter (cache 24h)
├── ui.py                # Apresentação do menu (cores, emojis, molduras)
└── usage.py             # Uso/saldo no OpenRouter + validação de chave
```

Cada arquivo tem uma responsabilidade única e clara. Novas funcionalidades
devem respeitar essa separação.

---

## 5. Claude Code neste projeto

O openia lança o Claude Code com `--dangerously-skip-permissions` (YOLO MODE)
por padrão. O menu interativo do openia já é o gate de consentimento — a pessoa
escolheu o projeto e confirmou. Portanto:

- **Não peça permissão para nada** — edite, execute comandos, leia e escreva
  arquivos diretamente.
- **Use acesso total às ferramentas** — Bash, PowerShell, Edit, Write, Glob,
  Grep, Read e todas as demais estão liberadas.
- **Siga os padrões de qualidade automaticamente** — não espere o usuário pedir
  qualidade; este CLAUDE.md é o contrato permanente.

---

## 6. Checklist rápido antes de encerrar qualquer alteração

- [ ] A solução segue o padrão existente do repositório
- [ ] As responsabilidades continuam separadas por camada
- [ ] Nenhum segredo, token ou dado sensível foi exposto
- [ ] Contratos (`AIInterface`, APIs, formatos) foram preservados
- [ ] Testes passam (`python -m pytest -q`)
- [ ] `IA.md` atualizado com entrada datada (se a mudança for relevante)
- [ ] Commit no formato `tipo: descricao` com explicação do que e por que
- [ ] O próximo mantenedor consegue entender a decisão sem reler a conversa