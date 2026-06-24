@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
rem ============================================================================
rem  openia-command.cmd - MODELO do comando "openia" para o CMD.
rem
rem  ATENCAO: este NAO e o instalador, nem o comando final. O instalador
rem  (install-openia-cmd.cmd) copia este arquivo para o PATH como openia.cmd e
rem  troca a linha __OPENIA_HOME__ abaixo pelo caminho real do projeto. Assim o
rem  comando fica autossuficiente: nao depende de variavel de ambiente carregar.
rem
rem  >>> O QUE FAZ <<<
rem    Abre o menu do openia (start_app.py) a partir da pasta onde o projeto
rem    foi instalado, nao importa em qual pasta voce esteja. Os argumentos sao
rem    repassados ao start_app (ex.: "openia key", "openia list").
rem
rem  Para qual terminal: CMD (Windows). Em Bash/Zsh use
rem  bash-zsh/install-openia-bash-zsh.sh; em PowerShell use
rem  powershell/install-openia-powershell.ps1.
rem  Requisitos: Python no PATH (python ou py).
rem ============================================================================

set "OPENIA_HOME=__OPENIA_HOME__"

if not exist "%OPENIA_HOME%\start_app.py" (
  echo [openia X] Nao encontrei start_app.py em: %OPENIA_HOME%
  echo [openia ] A pasta do projeto pode ter sido movida. Reinstale: install-openia-cmd.cmd
  exit /b 1
)

rem --- escolhe o lancador de Python disponivel ---
set "PYEXE="
where py >nul 2>nul && set "PYEXE=py"
if not defined PYEXE (
  where python >nul 2>nul && set "PYEXE=python"
)
if not defined PYEXE (
  echo [openia X] Python nao encontrado no PATH. Instale o Python 3.10+ e tente de novo.
  exit /b 1
)

rem --- roda o start_app a partir da raiz do projeto, repassando os argumentos ---
pushd "%OPENIA_HOME%"
%PYEXE% "%OPENIA_HOME%\start_app.py" %*
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
