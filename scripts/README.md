# Comando global `openia`

Estes scripts registram o comando **`openia`** no seu terminal. Depois de
instalar, você abre o menu do openia digitando `openia` **em qualquer pasta** —
sem precisar navegar até o projeto nem lembrar de `python start_app.py`.

É o mesmo padrão dos instaladores do *Felixo System Design*, adaptado: em vez de
baixar um repositório, o comando roda o `start_app.py` desta cópia local do
projeto. O caminho do projeto é detectado automaticamente na hora da instalação
(a partir da posição destes scripts), então você não digita caminho nenhum.

## Qual instalador usar?

Escolha pelo seu terminal — você só precisa de **um**:

| Terminal | Instalador | Como rodar |
| --- | --- | --- |
| **PowerShell** (Windows/Linux/macOS) | `powershell/install-openia-powershell.ps1` | `./install-openia-powershell.ps1` |
| **CMD** (Prompt clássico do Windows) | `cmd/install-openia-cmd.cmd` | duplo clique ou `install-openia-cmd.cmd` |
| **Bash / Zsh** (Linux, macOS, Git Bash, WSL) | `bash-zsh/install-openia-bash-zsh.sh` | `bash install-openia-bash-zsh.sh` |

Não sabe qual é o seu? Se você abriu o "Prompt de Comando", é **CMD**. Se abriu o
"Windows PowerShell" / "Terminal", é **PowerShell**. No Linux/macOS quase sempre
é **Bash ou Zsh**.

## Passo a passo

1. Abra o seu terminal **dentro** da pasta do instalador correspondente.
2. Rode o instalador (veja a tabela acima).
3. **Abra um terminal novo** (ou recarregue o perfil, como o instalador indica).
4. Em qualquer pasta, digite:

   ```
   openia          # abre o menu interativo
   openia key      # configura a chave do OpenRouter
   openia list     # lista as interfaces de IA suportadas
   ```

Qualquer argumento é repassado ao `start_app.py`, então tudo que funcionava com
`python start_app.py ...` funciona com `openia ...`.

## "openia não é reconhecido" depois de instalar

O instalador grava o comando no PATH, mas **terminais já abertos não enxergam o
PATH novo** — você precisa de um terminal que tenha iniciado *depois* da
instalação.

- **Abra um terminal totalmente novo** e tente de novo.
- **Usa VS Code, Cursor ou um terminal integrado?** Abrir só uma aba nova **não
  basta**: o terminal herda o ambiente do editor, que continua em segundo plano
  com o PATH antigo. **Feche o editor por inteiro** e reabra — ou faça
  **logoff/login** no Windows, que resolve em qualquer caso.
- **Quero usar agora, sem fechar nada:** injete o PATH só nesta sessão e rode:

  ```cmd
  set "PATH=%LOCALAPPDATA%\openia;%PATH%"
  openia
  ```

  (No PowerShell: `$env:Path = "$env:LOCALAPPDATA\openia;$env:Path"; openia`.)

## Desinstalar

| Terminal | Comando |
| --- | --- |
| PowerShell | `./install-openia-powershell.ps1 -Uninstall` |
| CMD | `install-openia-cmd.cmd --uninstall` |
| Bash / Zsh | `bash install-openia-bash-zsh.sh --uninstall` |

## Observações

- **Requisito:** Python 3.10+ no PATH (`python`, `py` ou `python3`). O próprio
  `start_app.py` instala as dependências (como o `typer`) na primeira execução.
- **Onde ficam suas chaves:** em `openia/keys.json`, dentro do projeto — não
  importa de qual pasta você rode `openia`, a configuração é a mesma.
- **Se você mover a pasta do projeto:** rode o instalador de novo para atualizar
  o caminho (ele fica embutido no comando gerado).
- **Acentos no caminho:** o comando funciona mesmo com o projeto numa pasta
  acentuada (ex.: `Programação`) — a saída é forçada para UTF-8.
- O CMD usa dois arquivos (`install-openia-cmd.cmd` e `openia-command.cmd`)
  porque, no CMD, um comando precisa ser um arquivo no PATH. No PowerShell e no
  Bash/Zsh o instalador escreve uma função no seu perfil, então é um arquivo só.
