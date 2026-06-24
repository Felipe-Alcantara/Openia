<#
.SYNOPSIS
  Instalador do comando global "openia".

  >>> PARA QUAL TERMINAL <<<
    Shell:    PowerShell (Windows PowerShell 5.1+ ou PowerShell 7+)
    Sistemas: Windows, Linux, macOS
    Use os outros instaladores se o seu terminal for:
      - Bash ou Zsh (Linux, macOS, Git Bash, WSL) -> bash-zsh/install-openia-bash-zsh.sh
      - CMD (Prompt classico do Windows)          -> cmd/install-openia-cmd.cmd

.DESCRIPTION
  Adiciona a funcao "openia" ao seu $PROFILE do PowerShell. Depois de instalado,
  digite "openia" em QUALQUER pasta para abrir o menu do openia (start_app.py).
  Os argumentos sao repassados ao start_app (ex.: "openia key", "openia list").

  O caminho do projeto e detectado a partir da localizacao deste instalador
  (duas pastas acima) e gravado na funcao. Nada de caminho digitado a mao.

.PARAMETER Uninstall
  Remove a funcao "openia" do $PROFILE.

.EXAMPLE
  .\install-openia-powershell.ps1
  .\install-openia-powershell.ps1 -Uninstall

.NOTES
  Requisitos: PowerShell 5.1+ e Python 3.10+ no PATH.
#>
[CmdletBinding()]
param(
  [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'

$BlockBegin = '# >>> openia command (managed by install-openia.ps1) >>>'
$BlockEnd   = '# <<< openia command (managed by install-openia.ps1) <<<'

# Raiz do projeto = duas pastas acima deste script (scripts\powershell\..\..).
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path

function Write-Info  ($m) { Write-Host "[openia-install] $m"    -ForegroundColor Cyan }
function Write-Ok    ($m) { Write-Host "[openia-install OK] $m" -ForegroundColor Green }
function Write-Warn2 ($m) { Write-Host "[openia-install !] $m"  -ForegroundColor Yellow }
function Write-Err2  ($m) { Write-Host "[openia-install X] $m"  -ForegroundColor Red }

# Bloco com a definicao da funcao openia. O caminho da raiz e embutido como
# literal (entre aspas simples) para nao depender de variaveis em runtime.
$OpeniaBlock = @"
$BlockBegin
function openia {
    `$openiaHome = '$ProjectRoot'
    `$startApp = Join-Path `$openiaHome 'start_app.py'

    if (-not (Test-Path `$startApp)) {
        Write-Host "[openia X] Nao encontrei start_app.py em: `$openiaHome" -ForegroundColor Red
        Write-Host "[openia ] A pasta do projeto pode ter sido movida. Reinstale o comando." -ForegroundColor Cyan
        return
    }

    `$py = `$null
    foreach (`$cand in @('py','python','python3')) {
        if (Get-Command `$cand -ErrorAction SilentlyContinue) { `$py = `$cand; break }
    }
    if (-not `$py) {
        Write-Host "[openia X] Python nao encontrado no PATH. Instale o Python 3.10+." -ForegroundColor Red
        return
    }

    # Roda a partir da raiz do projeto, repassando todos os argumentos.
    Push-Location `$openiaHome
    try {
        & `$py `$startApp @args
    } finally {
        Pop-Location
    }
}
$BlockEnd
"@

function Get-ProfilePath {
    if ($PROFILE -and $PROFILE.CurrentUserAllHosts) { return $PROFILE.CurrentUserAllHosts }
    return $PROFILE
}

function Remove-OpeniaBlock([string]$path) {
    if (-not (Test-Path $path)) { return }
    $content = Get-Content -Path $path -Raw
    $pattern = [regex]::Escape($BlockBegin) + '.*?' + [regex]::Escape($BlockEnd)
    $cleaned = [regex]::Replace($content, $pattern, '', 'Singleline')
    $cleaned = $cleaned.TrimEnd() + "`r`n"
    Set-Content -Path $path -Value $cleaned -NoNewline
}

function Invoke-Install {
    if (-not (Test-Path (Join-Path $ProjectRoot 'start_app.py'))) {
        Write-Err2 "Nao encontrei start_app.py em: $ProjectRoot"
        Write-Info 'Rode este instalador de dentro de scripts\powershell do projeto openia.'
        exit 1
    }
    $py = $null
    foreach ($cand in @('py','python','python3')) {
        if (Get-Command $cand -ErrorAction SilentlyContinue) { $py = $cand; break }
    }
    if (-not $py) { Write-Warn2 'Python nao encontrado no PATH. Instale o Python 3.10+ antes de usar "openia".' }

    $profilePath = Get-ProfilePath
    $dir = Split-Path -Parent $profilePath
    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    if (-not (Test-Path $profilePath)) { New-Item -ItemType File -Force -Path $profilePath | Out-Null }

    $action = 'instalado'
    if ((Get-Content -Path $profilePath -Raw -ErrorAction SilentlyContinue) -match [regex]::Escape($BlockBegin)) {
        $action = 'atualizado'
        Remove-OpeniaBlock $profilePath
    }

    Add-Content -Path $profilePath -Value ("`r`n" + $OpeniaBlock)

    Write-Ok   "Comando `"openia`" $action em: $profilePath"
    Write-Info "Projeto: $ProjectRoot"
    Write-Info "Abra um novo terminal ou rode: . `"$profilePath`""
    Write-Info "Depois, em QUALQUER pasta:"
    Write-Info "  openia        -> abre o menu interativo"
    Write-Info "  openia key    -> configura a chave do OpenRouter"
    Write-Info "  openia list   -> lista as interfaces de IA"
}

function Invoke-Uninstall {
    $profilePath = Get-ProfilePath
    if ((Test-Path $profilePath) -and ((Get-Content -Path $profilePath -Raw) -match [regex]::Escape($BlockBegin))) {
        Remove-OpeniaBlock $profilePath
        Write-Ok "Comando `"openia`" removido de: $profilePath"
        Write-Info 'Abra um novo terminal para aplicar.'
    } else {
        Write-Warn2 "Nenhuma instalacao do comando `"openia`" encontrada em: $profilePath"
    }
}

if ($Uninstall) { Invoke-Uninstall } else { Invoke-Install }
