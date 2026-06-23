"""Apresentação do menu interativo: molduras, cores e emojis.

Isola a aparência do terminal da lógica do CLI (``cli.py``). Usa caixas Unicode
e cores do Typer/Click. As funções aqui só desenham e leem entrada — não sabem
nada sobre interfaces de IA ou modelos.
"""

from __future__ import annotations

import shutil

import typer

# Largura alvo da moldura, limitada ao terminal para não estourar a linha.
_MAX_WIDTH = 64


def _width() -> int:
    cols = shutil.get_terminal_size((80, 24)).columns
    return min(_MAX_WIDTH, max(40, cols - 2))


def _visible_len(text: str) -> int:
    """Comprimento de exibição aproximado, contando emojis como 2 colunas.

    A maioria dos emojis ocupa duas células no terminal; somamos 1 extra para
    cada caractere fora do plano básico, o suficiente para alinhar a moldura.
    """
    extra = sum(1 for ch in text if ord(ch) > 0x2600)
    return len(text) + extra


def banner(titulo: str, subtitulo: str | None = None) -> None:
    """Desenha um cabeçalho emoldurado em destaque."""
    w = _width()
    top = "╭" + "─" * (w - 2) + "╮"
    bottom = "╰" + "─" * (w - 2) + "╯"
    typer.secho(top, fg=typer.colors.CYAN)
    _linha_centralizada(titulo, w, bold=True, fg=typer.colors.CYAN)
    if subtitulo:
        _linha_centralizada(subtitulo, w, fg=typer.colors.BRIGHT_BLACK)
    typer.secho(bottom, fg=typer.colors.CYAN)


def _linha_centralizada(texto: str, w: int, bold: bool = False, fg: str | None = None) -> None:
    interior = w - 2
    pad = interior - _visible_len(texto)
    left = max(pad // 2, 0)
    right = max(pad - left, 0)
    typer.secho("│", fg=typer.colors.CYAN, nl=False)
    typer.secho(" " * left + texto + " " * right, bold=bold, fg=fg, nl=False)
    typer.secho("│", fg=typer.colors.CYAN)


def section(titulo: str) -> None:
    """Título de seção com uma régua leve abaixo."""
    typer.echo()
    typer.secho(f" {titulo}", bold=True, fg=typer.colors.BRIGHT_WHITE)
    typer.secho(" " + "─" * (_width() - 2), fg=typer.colors.BRIGHT_BLACK)


def option(numero: int, rotulo: str, emoji: str = "", dim: str | None = None) -> None:
    """Linha de uma opção: número em destaque, rótulo e nota opcional esmaecida.

    A nota (``dim``) vai na linha de baixo, indentada, para a lista respirar.
    """
    prefixo = f"  {typer.style(f'[{numero}]', fg=typer.colors.GREEN, bold=True)} "
    cabeca = f"{emoji} " if emoji else ""
    typer.echo(prefixo + cabeca + rotulo)
    if dim is not None:
        typer.secho(f"        {dim}", fg=typer.colors.BRIGHT_BLACK)


def back_option(numero: int, rotulo: str) -> None:
    """Opção de voltar/sair, em tom mais discreto."""
    prefixo = f"  {typer.style(f'[{numero}]', fg=typer.colors.YELLOW, bold=True)} "
    typer.secho(prefixo + rotulo, fg=typer.colors.BRIGHT_BLACK)


def ask_number(prompt: str = "Sua escolha", default: int = 0) -> int:
    """Pede um número ao usuário, com seta e cor."""
    seta = typer.style("➜", fg=typer.colors.CYAN, bold=True)
    typer.echo()
    return typer.prompt(f"{seta} {prompt}", type=int, default=default)


def info(msg: str, emoji: str = "ℹ️") -> None:
    typer.secho(f"{emoji}  {msg}", fg=typer.colors.BRIGHT_CYAN)


def success(msg: str, emoji: str = "✅") -> None:
    typer.secho(f"{emoji}  {msg}", fg=typer.colors.GREEN)


def warn(msg: str, emoji: str = "⚠️") -> None:
    typer.secho(f"{emoji}  {msg}", fg=typer.colors.YELLOW)


def error(msg: str, emoji: str = "❌") -> None:
    typer.secho(f"{emoji}  {msg}", fg=typer.colors.RED, err=True)
