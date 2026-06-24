@echo off
setlocal EnableDelayedExpansion
rem ============================================================================
rem  install-openia-cmd.cmd - registra o comando "openia" no CMD.
rem
rem  >>> PARA QUAL TERMINAL <<<
rem    Shell:    CMD (Prompt de Comando classico)
rem    Sistemas: Windows
rem    Use os outros instaladores se o seu terminal for:
rem      - Bash ou Zsh (Linux, macOS, Git Bash, WSL) -> bash-zsh/install-openia-bash-zsh.sh
rem      - PowerShell (qualquer SO)                  -> powershell/install-openia-powershell.ps1
rem
rem  O que faz: copia openia-command.cmd (ao lado deste arquivo) para
rem  %LOCALAPPDATA%\openia como "openia.cmd", grava o caminho real do projeto
rem  DENTRO desse openia.cmd e adiciona a pasta ao PATH do usuario. Depois, abra
rem  um NOVO terminal e rode "openia" em qualquer pasta. O caminho fica embutido
rem  no proprio comando, entao nao depende de variavel de ambiente carregar.
rem
rem  >>> O CMD USA DOIS ARQUIVOS <<<
rem    install-openia-cmd.cmd (este) -> o INSTALADOR; voce roda uma vez.
rem    openia-command.cmd            -> o COMANDO "openia" em si, que este
rem                                     instalador copia para o PATH (como
rem                                     openia.cmd). Voce nao roda direto.
rem
rem  Uso:
rem    install-openia-cmd.cmd              instala
rem    install-openia-cmd.cmd --uninstall  remove
rem ============================================================================

set "SRC=%~dp0openia-command.cmd"
set "TARGET_DIR=%LOCALAPPDATA%\openia"
set "TARGET=%TARGET_DIR%\openia.cmd"

rem --- raiz do projeto = duas pastas acima deste script (scripts\cmd\..\..) ---
for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"

if /I "%~1"=="--uninstall" goto :uninstall
if /I "%~1"=="-u" goto :uninstall

if not exist "%SRC%" (
  echo [openia-install X] Nao encontrei openia-command.cmd ao lado deste instalador.
  exit /b 1
)

if not exist "%PROJECT_ROOT%\start_app.py" (
  echo [openia-install X] Nao encontrei start_app.py em: %PROJECT_ROOT%
  echo [openia-install ] Rode este instalador de dentro de scripts\cmd do projeto openia.
  exit /b 1
)

where py >nul 2>nul || where python >nul 2>nul
if errorlevel 1 echo [openia-install !] Aviso: Python nao esta no PATH. Instale o Python 3.10+ antes de usar "openia".

if not exist "%TARGET_DIR%" mkdir "%TARGET_DIR%"

rem --- copia o modelo trocando __OPENIA_HOME__ pelo caminho real do projeto ---
rem  Usa PowerShell com .Replace() (literal, sem regex) e grava em ANSI/CRLF.
rem  Le e grava em UTF-8 sem BOM; o openia.cmd faz "chcp 65001" para ler o
rem  caminho com acentos corretamente (ex.: pasta "Programacao").
powershell -NoProfile -Command ^
  "$c = [System.IO.File]::ReadAllText('%SRC%', [System.Text.Encoding]::UTF8);" ^
  "$c = $c.Replace('__OPENIA_HOME__', '%PROJECT_ROOT%');" ^
  "$enc = New-Object System.Text.UTF8Encoding($false);" ^
  "[System.IO.File]::WriteAllText('%TARGET%', $c, $enc)"
if not exist "%TARGET%" (
  echo [openia-install X] Falha ao gravar openia.cmd em %TARGET_DIR%.
  exit /b 1
)
echo [openia-install OK] Projeto embutido no comando: %PROJECT_ROOT%

rem --- adiciona ao PATH do usuario se ainda nao estiver ---
echo %PATH% | find /I "%TARGET_DIR%" >nul
if errorlevel 1 (
  for /f "skip=2 tokens=2,*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USER_PATH=%%B"
  if defined USER_PATH (
    setx PATH "!USER_PATH!;%TARGET_DIR%" >nul
  ) else (
    setx PATH "%TARGET_DIR%" >nul
  )
  echo [openia-install OK] Pasta adicionada ao PATH do usuario: %TARGET_DIR%
) else (
  echo [openia-install] Pasta ja estava no PATH: %TARGET_DIR%
)

echo [openia-install OK] Comando "openia" instalado.
echo [openia-install] Abra um NOVO terminal e, em QUALQUER pasta, rode:
echo [openia-install]   openia          -^> abre o menu interativo
echo [openia-install]   openia key      -^> configura a chave do OpenRouter
echo [openia-install]   openia list     -^> lista as interfaces de IA
exit /b 0

:uninstall
if exist "%TARGET%" del /q "%TARGET%"
if exist "%TARGET_DIR%" rmdir "%TARGET_DIR%" 2>nul
echo [openia-install OK] openia.cmd removido de %TARGET_DIR%.
echo [openia-install] Remova manualmente "%TARGET_DIR%" do PATH (se desejar) em:
echo [openia-install]   Painel de Controle ^> Sistema ^> Variaveis de Ambiente.
exit /b 0
