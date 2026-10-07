"""Smoke da geração de imagem pelo pacote ``openia`` INSTALADO.

Roda o ``openia`` que está no PATH (o pacote instalado, não este checkout) e
confere o contrato público do ``openia image`` em duas execuções reais:

1. **geração** — JSON versionado, MIME permitido, bytes iguais no JSON e no
   disco, caminho absoluto dentro da pasta pedida, timestamps em ordem,
   assinatura do arquivo e nenhuma sobra temporária;
2. **timeout forçado** (``--timeout 1 --retries 0``) — exit 124, código
   ``timeout`` e pasta de saída vazia.

Nas duas, stdout e stderr são varridos atrás da chave, de headers de
autenticação, de URLs, de base64 longo (imagem dentro do log) e da pasta
pessoal. O relatório final tem só códigos, números e booleanos: pode ir para
log, Notion ou issue sem revisão.

Uso (a chave vem do ambiente e nunca é impressa)::

    OPENROUTER_API_KEY=... python scripts/smoke_imagem_empacotada.py \\
        --model openai/gpt-image-1-mini --work-dir /tmp/smoke-openia

Sai com 0 só quando todas as checagens passam. A geração real gasta crédito do
OpenRouter: rode com orçamento combinado.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

SCHEMA_VERSION = 1
PROMPT = "um quadrado azul simples sobre fundo branco"

# Assinatura (magic number) de cada MIME que o contrato aceita.
ASSINATURAS = {
    "image/png": lambda dados: dados.startswith(b"\x89PNG\r\n\x1a\n"),
    "image/jpeg": lambda dados: dados.startswith(b"\xff\xd8\xff"),
    "image/webp": lambda dados: dados[:4] == b"RIFF" and dados[8:12] == b"WEBP",
    "image/svg+xml": lambda dados: b"<svg" in dados[:2048].lower(),
}

_HEADER_AUTENTICACAO = re.compile(r"authorization|bearer\s+\S|x-api-key", re.IGNORECASE)
_URL = re.compile(r"https?://", re.IGNORECASE)
# Base64 de imagem ocupa milhares de caracteres seguidos; 200 já é suspeito.
_BASE64_LONGO = re.compile(r"[A-Za-z0-9+/=]{200,}")


def procurar_vazamentos(
    textos: list[str], *, chave: str | None, pasta_pessoal: str | None
) -> dict[str, bool]:
    """Diz, por categoria, se algum texto vazou algo que não pode sair.

    ``True`` = vazou. Devolve só booleanos para o relatório não carregar o que
    encontrou.
    """
    junto = "\n".join(textos)
    return {
        "chave": bool(chave) and chave in junto,
        "header_autenticacao": bool(_HEADER_AUTENTICACAO.search(junto)),
        "url": bool(_URL.search(junto)),
        "base64_longo": bool(_BASE64_LONGO.search(junto)),
        "pasta_pessoal": bool(pasta_pessoal) and pasta_pessoal in junto,
    }


def _timestamp(valor: object) -> datetime | None:
    if not isinstance(valor, str):
        return None
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return None


def verificar_sucesso(envelope: object, pasta: Path) -> dict[str, object]:
    """Confere o envelope de uma geração bem-sucedida contra o disco."""
    checagens: dict[str, bool] = {}
    detalhes: dict[str, object] = {}
    valido = isinstance(envelope, dict)
    checagens["json_objeto"] = valido
    envelope = envelope if valido else {}

    checagens["versao"] = envelope.get("version") == SCHEMA_VERSION
    checagens["ok_true"] = envelope.get("ok") is True
    criado = _timestamp(envelope.get("createdAt"))
    concluido = _timestamp(envelope.get("completedAt"))
    checagens["timestamps"] = bool(criado and concluido and criado <= concluido)

    saidas = envelope.get("outputs")
    saidas = saidas if isinstance(saidas, list) else []
    checagens["tem_saida"] = len(saidas) > 0
    pasta_real = pasta.resolve()
    caminhos: set[Path] = set()
    por_saida = []
    for saida in saidas:
        saida = saida if isinstance(saida, dict) else {}
        bruto = saida.get("path")
        caminho = Path(bruto) if isinstance(bruto, str) else None
        existe = bool(caminho and caminho.is_file())
        dados = caminho.read_bytes() if existe and caminho else b""
        mime = saida.get("mime")
        assinatura = ASSINATURAS.get(mime) if isinstance(mime, str) else None
        if caminho:
            caminhos.add(caminho.resolve() if existe else caminho)
        por_saida.append(
            {
                "absoluto": bool(caminho and caminho.is_absolute()),
                "dentro_da_pasta": bool(existe and caminho and caminho.resolve().parent == pasta_real),
                "existe": existe,
                "mime_permitido": assinatura is not None,
                "bytes_json_igual_disco": existe and saida.get("bytes") == len(dados),
                "assinatura_confere": bool(assinatura and assinatura(dados)),
            }
        )
        detalhes.setdefault("arquivos", []).append({"mime": mime, "bytes": len(dados)})
    for nome in ("absoluto", "dentro_da_pasta", "existe", "mime_permitido", "bytes_json_igual_disco", "assinatura_confere"):
        checagens[nome] = bool(por_saida) and all(item[nome] for item in por_saida)

    # Limpeza: na pasta só podem sobrar os arquivos que o JSON declarou.
    sobras = [item for item in pasta.iterdir() if item.resolve() not in caminhos] if pasta.is_dir() else []
    checagens["sem_sobra_temporaria"] = not sobras
    detalhes["sobras"] = len(sobras)
    return {"checagens": checagens, **detalhes}


def verificar_timeout(exit_code: int, envelope: object, pasta: Path) -> dict[str, object]:
    """Confere o timeout forçado: código próprio, exit 124 e nada no disco."""
    envelope = envelope if isinstance(envelope, dict) else {}
    erro = envelope.get("error") if isinstance(envelope.get("error"), dict) else {}
    restantes = list(pasta.iterdir()) if pasta.is_dir() else []
    return {
        "codigo": erro.get("code"),
        "checagens": {
            "exit_124": exit_code == 124,
            "versao": envelope.get("version") == SCHEMA_VERSION,
            "ok_false": envelope.get("ok") is False,
            "codigo_timeout": erro.get("code") == "timeout",
            "pasta_vazia": not restantes,
        },
        "sobras": len(restantes),
    }


def _executar(comando: list[str], limite: float) -> tuple[int, str, str, float]:
    inicio = time.monotonic()
    processo = subprocess.run(comando, capture_output=True, text=True, timeout=limite, check=False)
    return processo.returncode, processo.stdout, processo.stderr, round(time.monotonic() - inicio, 3)


def _ler_json(texto: str) -> object:
    try:
        return json.loads(texto)
    except ValueError:
        return None


def _instalado_fora_do_checkout(executavel: str) -> bool:
    """O ``openia`` do PATH não pode ser o deste checkout (aí não seria o pacote)."""
    checkout = Path(__file__).resolve().parents[1]
    return checkout not in Path(executavel).resolve().parents


def _codigo_de_erro(envelope: object) -> str | None:
    erro = envelope.get("error") if isinstance(envelope, dict) else None
    return erro.get("code") if isinstance(erro, dict) else None


def executar_smoke(
    modelo: str, pasta_trabalho: Path, *, timeout_geracao: float, qualidade: str | None = "low"
) -> dict[str, object]:
    """Roda as duas execuções e monta o relatório seguro."""
    executavel = shutil.which("openia")
    relatorio: dict[str, object] = {
        "version": 1,
        "plataforma": f"{platform.system()} {platform.release()} {platform.machine()}",
        "python": platform.python_version(),
        "modelo": modelo,
    }
    if not executavel:
        relatorio["ok"] = False
        relatorio["erro"] = "openia_nao_instalado"
        return relatorio

    _, versao, _, _ = _executar([executavel, "--version"], 60)
    relatorio["openia_versao"] = versao.strip()[:80]
    relatorio["instalado_fora_do_checkout"] = _instalado_fora_do_checkout(executavel)

    pasta_ok = pasta_trabalho / "geracao"
    pasta_timeout = pasta_trabalho / "timeout"
    for pasta in (pasta_ok, pasta_timeout):
        pasta.mkdir(parents=True, exist_ok=True)

    base = [executavel, "image", "--prompt", PROMPT, "--model", modelo, "--json"]
    qualidade_args = ["--quality", qualidade] if qualidade else []
    exit_ok, out_ok, err_ok, dur_ok = _executar(
        [*base, "--output-dir", str(pasta_ok), *qualidade_args, "--retries", "0", "--timeout", str(timeout_geracao)],
        timeout_geracao + 60,
    )
    envelope_ok = _ler_json(out_ok)
    geracao = verificar_sucesso(envelope_ok, pasta_ok)
    geracao["checagens"]["exit_0"] = exit_ok == 0
    # Na falha, o código público diz o porquê (ex.: account_limit = HTTP 402).
    relatorio["geracao"] = {"exit": exit_ok, "duracao_s": dur_ok, "codigo": _codigo_de_erro(envelope_ok), **geracao}

    exit_to, out_to, err_to, dur_to = _executar(
        [*base, "--output-dir", str(pasta_timeout), "--timeout", "1", "--retries", "0"], 120
    )
    relatorio["timeout"] = {"exit": exit_to, "duracao_s": dur_to, **verificar_timeout(exit_to, _ler_json(out_to), pasta_timeout)}

    relatorio["vazamentos"] = procurar_vazamentos(
        [out_ok, err_ok, out_to, err_to],
        chave=os.environ.get("OPENROUTER_API_KEY"),
        pasta_pessoal=str(Path.home()) if Path.home() not in pasta_trabalho.resolve().parents else None,
    )
    relatorio["ok"] = (
        relatorio["instalado_fora_do_checkout"] is True
        and all(relatorio["geracao"]["checagens"].values())
        and all(relatorio["timeout"]["checagens"].values())
        and not any(relatorio["vazamentos"].values())
    )
    return relatorio


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke da geração de imagem pelo pacote openia instalado.")
    parser.add_argument("--model", default="openai/gpt-image-1-mini")
    parser.add_argument("--work-dir", required=True, help="Pasta descartável para as saídas.")
    parser.add_argument("--timeout", type=float, default=180.0, help="Teto da geração real, em segundos.")
    parser.add_argument("--quality", default="low", help="Qualidade pedida; vazio não envia (modelo sem esse parâmetro).")
    argumentos = parser.parse_args(argv)

    relatorio = executar_smoke(
        argumentos.model,
        Path(argumentos.work_dir).resolve(),
        timeout_geracao=argumentos.timeout,
        qualidade=argumentos.quality or None,
    )
    print(json.dumps(relatorio, ensure_ascii=False, indent=1))
    return 0 if relatorio.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
