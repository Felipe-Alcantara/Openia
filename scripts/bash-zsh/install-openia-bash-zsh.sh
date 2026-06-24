#!/usr/bin/env bash
#
# Instalador do comando global "openia".
#
# >>> PARA QUAL TERMINAL <<<
#   Shell:    Bash ou Zsh
#   Sistemas: Linux, macOS, Git Bash (Windows), WSL (Windows)
#   Use os outros instaladores se o seu terminal for:
#     - PowerShell (qualquer SO) -> powershell/install-openia-powershell.ps1
#     - CMD (Prompt classico do Windows) -> cmd/install-openia-cmd.cmd
#
# O que faz: injeta a funcao "openia" no seu .bashrc (ou .zshrc). Depois de
# instalado, digite "openia" em QUALQUER pasta para abrir o menu do openia
# (start_app.py). Os argumentos sao repassados ao start_app (ex.: "openia key",
# "openia list").
#
# O caminho do projeto e detectado a partir da localizacao deste instalador
# (duas pastas acima) e gravado na funcao. Nada de caminho digitado a mao.
#
# Uso:
#   ./install-openia-bash-zsh.sh              instala (ou atualiza) o comando
#   ./install-openia-bash-zsh.sh --uninstall  remove o comando
#   ./install-openia-bash-zsh.sh --help       mostra esta ajuda
#
# Requisitos: bash ou zsh, e Python 3.10+ (python3 ou python) no PATH.

set -euo pipefail

BLOCK_BEGIN="# >>> openia command (managed by install-openia.sh) >>>"
BLOCK_END="# <<< openia command (managed by install-openia.sh) <<<"

# Raiz do projeto = duas pastas acima deste script (scripts/bash-zsh/../..).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# --- cores do instalador ---
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  C_RESET=$'\033[0m'; C_INFO=$'\033[1;34m'; C_OK=$'\033[1;32m'
  C_WARN=$'\033[1;33m'; C_ERR=$'\033[1;31m'; C_DIM=$'\033[2m'
else
  C_RESET=''; C_INFO=''; C_OK=''; C_WARN=''; C_ERR=''; C_DIM=''
fi
log()  { printf '%s[openia-install]%s %s\n'   "$C_INFO" "$C_RESET" "$*"; }
ok()   { printf '%s[openia-install ✓]%s %s\n' "$C_OK"   "$C_RESET" "$*"; }
warn() { printf '%s[openia-install ⚠]%s %s\n' "$C_WARN" "$C_RESET" "$*" >&2; }
err()  { printf '%s[openia-install ✗]%s %s\n' "$C_ERR"  "$C_RESET" "$*" >&2; }

print_help() {
  sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
}

# Descobre o arquivo de configuracao do shell do usuario.
detect_rc_file() {
  local shell_name
  shell_name="$(basename "${SHELL:-}")"
  case "$shell_name" in
    zsh) printf '%s\n' "${ZDOTDIR:-$HOME}/.zshrc" ;;
    bash)
      if [ "$(uname -s)" = "Darwin" ] && [ -f "$HOME/.bash_profile" ]; then
        printf '%s\n' "$HOME/.bash_profile"
      else
        printf '%s\n' "$HOME/.bashrc"
      fi ;;
    *)
      if   [ -f "$HOME/.zshrc"  ]; then printf '%s\n' "$HOME/.zshrc"
      elif [ -f "$HOME/.bashrc" ]; then printf '%s\n' "$HOME/.bashrc"
      else printf '%s\n' "$HOME/.profile"; fi ;;
  esac
}

check_deps() {
  if [ ! -f "$PROJECT_ROOT/start_app.py" ]; then
    err "Nao encontrei start_app.py em: $PROJECT_ROOT"
    err "Rode este instalador de dentro de scripts/bash-zsh do projeto openia."
    exit 1
  fi
  if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
    warn "Python nao encontrado no PATH. Instale o Python 3.10+ antes de usar \"openia\"."
  fi
}

# Gera o bloco com a definicao da funcao openia. O caminho da raiz e embutido
# como literal entre aspas simples para nao depender de variaveis em runtime.
openia_block() {
  cat <<BLOCK
$BLOCK_BEGIN
openia() {
  local openia_home='$PROJECT_ROOT'
  local start_app="\$openia_home/start_app.py"

  if [ ! -f "\$start_app" ]; then
    printf '[openia ✗] Nao encontrei start_app.py em: %s\n' "\$openia_home" >&2
    printf '[openia ] A pasta do projeto pode ter sido movida. Reinstale o comando.\n' >&2
    return 1
  fi

  local py=
  if   command -v python3 >/dev/null 2>&1; then py=python3
  elif command -v python  >/dev/null 2>&1; then py=python
  else
    printf '[openia ✗] Python nao encontrado no PATH. Instale o Python 3.10+.\n' >&2
    return 1
  fi

  # Roda a partir da raiz do projeto, repassando todos os argumentos.
  ( cd "\$openia_home" && "\$py" "\$start_app" "\$@" )
}
$BLOCK_END
BLOCK
}

remove_block() {
  local rc_file="$1"
  [ -f "$rc_file" ] || return 0
  if grep -qF "$BLOCK_BEGIN" "$rc_file"; then
    local tmp
    tmp="$(mktemp)"
    awk -v b="$BLOCK_BEGIN" -v e="$BLOCK_END" '
      $0 == b {skip=1; next}
      $0 == e {skip=0; next}
      skip != 1 {print}
    ' "$rc_file" > "$tmp"
    cat "$tmp" > "$rc_file"
    rm -f "$tmp"
  fi
}

install() {
  check_deps
  local rc_file
  rc_file="$(detect_rc_file)"
  touch "$rc_file"

  local action="instalado"
  if grep -qF "$BLOCK_BEGIN" "$rc_file"; then
    action="atualizado"
    remove_block "$rc_file"
  fi

  { printf '\n'; openia_block; } >> "$rc_file"

  ok "Comando \"openia\" $action em: $rc_file"
  log "Projeto: ${C_DIM}${PROJECT_ROOT}${C_RESET}"
  log "Abra um novo terminal ou rode: ${C_DIM}source \"$rc_file\"${C_RESET}"
  log "Depois, em QUALQUER pasta:"
  log "  ${C_DIM}openia${C_RESET}        -> abre o menu interativo"
  log "  ${C_DIM}openia key${C_RESET}    -> configura a chave do OpenRouter"
  log "  ${C_DIM}openia list${C_RESET}   -> lista as interfaces de IA"
}

uninstall() {
  local rc_file
  rc_file="$(detect_rc_file)"
  if [ -f "$rc_file" ] && grep -qF "$BLOCK_BEGIN" "$rc_file"; then
    remove_block "$rc_file"
    ok "Comando \"openia\" removido de: $rc_file"
    log "Abra um novo terminal para aplicar."
  else
    warn "Nenhuma instalacao do comando \"openia\" encontrada em: $rc_file"
  fi
}

main() {
  case "${1:-}" in
    --uninstall|-u) uninstall ;;
    --help|-h)      print_help ;;
    ""|--install)   install ;;
    *) err "Opcao desconhecida: $1"; print_help; exit 1 ;;
  esac
}

main "$@"
