"""Testes das checagens do smoke de imagem empacotado (sem rede e sem chave)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "smoke_imagem_empacotada.py"
_spec = importlib.util.spec_from_file_location("smoke_imagem_empacotada", _SCRIPT)
smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoke)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _envelope(caminho: Path, *, mime: str = "image/png", tamanho: int | None = None) -> dict:
    return {
        "version": 1,
        "ok": True,
        "requestId": "pedido-1",
        "model": "openai/gpt-image-1-mini",
        "outputs": [{"path": str(caminho), "mime": mime, "bytes": len(PNG) if tamanho is None else tamanho}],
        "createdAt": "2026-10-07T12:00:00.000Z",
        "completedAt": "2026-10-07T12:00:11.000Z",
    }


def test_sucesso_confere_disco_assinatura_e_limpeza(tmp_path):
    arquivo = tmp_path / "openia-image-pedido-1-1.png"
    arquivo.write_bytes(PNG)

    resultado = smoke.verificar_sucesso(_envelope(arquivo), tmp_path)

    assert all(resultado["checagens"].values()), resultado["checagens"]
    assert resultado["arquivos"] == [{"mime": "image/png", "bytes": len(PNG)}]


@pytest.mark.parametrize(
    ("ajuste", "checagem"),
    [
        (lambda caminho: _envelope(caminho, tamanho=1), "bytes_json_igual_disco"),
        (lambda caminho: _envelope(caminho, mime="image/jpeg"), "assinatura_confere"),
        (lambda caminho: _envelope(caminho, mime="text/html"), "mime_permitido"),
        (lambda caminho: _envelope(Path(caminho.name)), "absoluto"),
        (lambda caminho: {**_envelope(caminho), "completedAt": "2026-10-07T11:00:00.000Z"}, "timestamps"),
        (lambda caminho: {**_envelope(caminho), "version": 2}, "versao"),
    ],
)
def test_sucesso_reprova_contrato_quebrado(tmp_path, ajuste, checagem):
    arquivo = tmp_path / "openia-image-pedido-1-1.png"
    arquivo.write_bytes(PNG)

    resultado = smoke.verificar_sucesso(ajuste(arquivo), tmp_path)

    assert resultado["checagens"][checagem] is False


def test_sucesso_acusa_temporario_esquecido(tmp_path):
    arquivo = tmp_path / "openia-image-pedido-1-1.png"
    arquivo.write_bytes(PNG)
    (tmp_path / ".openia-image-pedido-1-1.png.abc.tmp").write_bytes(b"parcial")

    resultado = smoke.verificar_sucesso(_envelope(arquivo), tmp_path)

    assert resultado["checagens"]["sem_sobra_temporaria"] is False
    assert resultado["sobras"] == 1


def test_saida_que_nao_e_json_reprova(tmp_path):
    resultado = smoke.verificar_sucesso(None, tmp_path)

    assert resultado["checagens"]["json_objeto"] is False
    assert resultado["checagens"]["tem_saida"] is False


def test_timeout_exige_codigo_exit_e_pasta_vazia(tmp_path):
    envelope = {"version": 1, "ok": False, "error": {"code": "timeout", "message": "tempo esgotado."}}

    limpo = smoke.verificar_timeout(124, envelope, tmp_path)
    (tmp_path / "sobra.tmp").write_bytes(b"x")
    sujo = smoke.verificar_timeout(1, envelope, tmp_path)

    assert all(limpo["checagens"].values())
    assert sujo["checagens"]["pasta_vazia"] is False
    assert sujo["checagens"]["exit_124"] is False


def test_vazamentos_acham_chave_header_url_base64_e_pasta_pessoal():
    chave = "sk-or-v1-" + "a" * 20
    vazou = smoke.procurar_vazamentos(
        [
            f"erro com {chave}",
            "Authorization: Bearer x",
            "https://cdn.exemplo/img.png?sig=1",
            "A" * 300,
            "/home/ana/segredo",
        ],
        chave=chave,
        pasta_pessoal="/home/ana",
    )

    assert vazou == {
        "chave": True,
        "header_autenticacao": True,
        "url": True,
        "base64_longo": True,
        "pasta_pessoal": True,
    }


def test_saida_limpa_nao_acusa_nada():
    texto = '{"version": 1, "ok": false, "error": {"code": "timeout", "message": "tempo esgotado."}}'

    vazou = smoke.procurar_vazamentos([texto, ""], chave="sk-or-v1-segredo", pasta_pessoal="/home/ana")

    assert not any(vazou.values())
