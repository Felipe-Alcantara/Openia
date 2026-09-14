"""Testes do contrato seguro de geração de imagens (sem chamadas reais)."""

from __future__ import annotations

import base64
import io
import json
import threading
import urllib.error

import pytest

from openia import image


VALID_KEY = "sk-or-v1-" + "a" * 40
PNG = b"\x89PNG\r\n\x1a\n" + b"imagem-de-teste"
PNG_B64 = base64.b64encode(PNG).decode("ascii")


class _Response:
    def __init__(self, payload, *, content_type: str | None = "application/json"):
        self._payload = payload
        self.status = 200
        self.headers = {"Content-Type": content_type} if content_type else {}

    def read(self, amount: int = -1):  # noqa: ARG002 - imita o objeto HTTP
        if isinstance(self._payload, bytes):
            return self._payload
        return json.dumps(self._payload).encode("utf-8")

    def getcode(self):
        return self.status

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _models_response(*, image_output: bool = True, supported: dict | None = None):
    return {
        "data": [
            {
                "id": "openai/gpt-image-1",
                "name": "GPT Image",
                "architecture": {
                    "input_modalities": ["text", "image"],
                    "output_modalities": ["image"] if image_output else ["text"],
                },
                "supported_parameters": supported
                or {
                    "n": {"type": "range", "min": 1, "max": 4},
                    "output_format": {"type": "enum", "values": ["png", "jpeg"]},
                },
            }
        ],
    }


def _request(output_dir, **kwargs):
    valores = {
        "model": "openai/gpt-image-1",
        "prompt": "um gato astronauta",
        "output_dir": output_dir,
        "idempotency_key": "pedido-1",
    }
    valores.update(kwargs)
    return image.ImageRequest(**valores)


def test_generate_grava_png_atomicamente_e_devolve_metadados(tmp_path, monkeypatch):
    chamadas = []

    def fake_urlopen(req, timeout=None):
        chamadas.append((req, timeout))
        if req.full_url.endswith("/models"):
            return _Response(_models_response())
        return _Response(
            {
                "created": 1748372400,
                "data": [{"b64_json": PNG_B64, "media_type": "image/png"}],
            }
        )

    monkeypatch.setattr(image.urllib.request, "urlopen", fake_urlopen)
    resultado = image.generate_image(_request(tmp_path), VALID_KEY)

    payload = resultado.to_dict()
    assert payload["version"] == 1
    assert payload["ok"] is True
    assert payload["model"] == "openai/gpt-image-1"
    assert payload["outputs"][0]["mime"] == "image/png"
    caminho = tmp_path / "openia-image-pedido-1-1.png"
    assert payload["outputs"][0]["path"] == str(caminho.resolve())
    assert caminho.read_bytes() == PNG
    assert payload["createdAt"].endswith("Z")
    assert payload["completedAt"].endswith("Z")
    assert not list(tmp_path.glob("*.tmp"))
    assert chamadas[1][0].headers["Authorization"] == f"Bearer {VALID_KEY}"
    assert chamadas[1][0].headers["Idempotency-key"] == "pedido-1"


def test_referencia_url_e_base64_formam_input_references(tmp_path):
    referencia_base64 = base64.b64encode(PNG).decode("ascii")
    requisicao = _request(
        tmp_path,
        references=("https://example.com/referencia.png", referencia_base64),
    )

    payload = image._build_payload(requisicao)

    assert payload["input_references"] == [
        {
            "type": "image_url",
            "image_url": {"url": "https://example.com/referencia.png"},
        },
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{referencia_base64}"},
        },
    ]


def test_generate_aceita_output_por_url_sem_expor_url(tmp_path, monkeypatch):
    url_privada = "https://storage.example/signed?token=nao-exibir"
    chamadas = []

    def fake_urlopen(req, timeout=None):
        chamadas.append(req)
        if req.full_url.endswith("/models"):
            return _Response(_models_response())
        if req.full_url == image.IMAGE_API_URL:
            return _Response(
                {"data": [{"url": url_privada, "media_type": "image/png"}]}
            )
        return _Response(PNG, content_type="image/png")

    monkeypatch.setattr(image.urllib.request, "urlopen", fake_urlopen)
    resultado = image.generate_image(_request(tmp_path), VALID_KEY)

    assert resultado.outputs[0].mime == "image/png"
    assert (tmp_path / "openia-image-pedido-1-1.png").read_bytes() == PNG
    assert url_privada not in json.dumps(resultado.to_dict())
    assert "Authorization" not in str(chamadas[-1].headers)


def test_generate_suporta_multiplas_saidas(tmp_path, monkeypatch):
    outra = b"\x89PNG\r\n\x1a\nsegunda"
    imagens = [
        {"b64_json": PNG_B64, "media_type": "image/png"},
        {
            "b64_json": base64.b64encode(outra).decode("ascii"),
            "media_type": "image/png",
        },
    ]

    def fake_urlopen(req, timeout=None):
        if req.full_url.endswith("/models"):
            return _Response(_models_response())
        return _Response({"data": imagens})

    monkeypatch.setattr(image.urllib.request, "urlopen", fake_urlopen)
    resultado = image.generate_image(_request(tmp_path, count=2), VALID_KEY)

    assert len(resultado.outputs) == 2
    assert (tmp_path / "openia-image-pedido-1-1.png").read_bytes() == PNG
    assert (tmp_path / "openia-image-pedido-1-2.png").read_bytes() == outra


def test_modelo_sem_saida_de_imagem_e_rejeitado_antes_do_post(tmp_path, monkeypatch):
    chamadas = []

    def fake_urlopen(req, timeout=None):
        chamadas.append(req.full_url)
        return _Response(_models_response(image_output=False))

    monkeypatch.setattr(image.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(image.ImageModelError) as exc:
        image.generate_image(_request(tmp_path), VALID_KEY)

    assert exc.value.code == "model_unsupported"
    assert image.IMAGE_API_URL not in chamadas


def test_referencia_exige_capability_de_entrada_do_modelo(tmp_path, monkeypatch):
    chamadas = []

    def fake_urlopen(req, timeout=None):
        chamadas.append(req.full_url)
        return _Response(
            {
                "data": [
                    {
                        "id": "openai/gpt-image-1",
                        "architecture": {
                            "input_modalities": ["text"],
                            "output_modalities": ["image"],
                        },
                        "supported_parameters": {
                            "input_references": {"type": "boolean"}
                        },
                    }
                ]
            }
        )

    monkeypatch.setattr(image.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(image.ImageModelError) as exc:
        image.generate_image(
            _request(tmp_path, references=("https://example.com/ref.png",)),
            VALID_KEY,
        )

    assert exc.value.code == "model_input_unsupported"
    assert image.IMAGE_API_URL not in chamadas


def test_provider_unsupported_tem_codigo_distinto_e_nao_expoe_corpo(
    tmp_path, monkeypatch
):
    segredo = VALID_KEY

    def fake_urlopen(req, timeout=None):
        if req.full_url.endswith("/models"):
            return _Response(_models_response())
        raise urllib.error.HTTPError(
            req.full_url,
            422,
            "Unprocessable Entity",
            {},
            io.BytesIO(f"provider unsupported token={segredo}".encode()),
        )

    monkeypatch.setattr(image.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(image.ImageProviderError) as exc:
        image.generate_image(_request(tmp_path, retries=0), segredo)

    assert exc.value.code == "provider_unsupported"
    assert segredo not in str(exc.value)
    assert segredo not in json.dumps(exc.value.to_dict())


def test_provider_inexistente_em_404_nao_e_confundido_com_modelo(tmp_path, monkeypatch):
    def fake_urlopen(req, timeout=None):
        if req.full_url.endswith("/models"):
            return _Response(_models_response())
        raise urllib.error.HTTPError(
            req.full_url,
            404,
            "Not Found",
            {},
            io.BytesIO(b"provider not found"),
        )

    monkeypatch.setattr(image.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(image.ImageProviderError) as exc:
        image.generate_image(
            _request(tmp_path, provider="provider-inexistente", retries=0),
            VALID_KEY,
        )

    assert exc.value.code == "provider_unsupported"


def test_saldo_insuficiente_tem_codigo_seguro_e_nao_cria_artefato(
    tmp_path, monkeypatch
):
    segredo = VALID_KEY

    def fake_urlopen(req, timeout=None):
        if req.full_url.endswith("/models"):
            return _Response(_models_response())
        raise urllib.error.HTTPError(
            req.full_url,
            402,
            "Payment Required",
            {},
            io.BytesIO(f"balance exhausted token={segredo}".encode()),
        )

    monkeypatch.setattr(image.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(image.ImageLimitError) as exc:
        image.generate_image(_request(tmp_path, retries=0), segredo)

    assert exc.value.code == "account_limit"
    assert not exc.value.retryable
    assert segredo not in str(exc.value)
    assert segredo not in json.dumps(image.error_payload(exc.value, "pedido-1"))
    assert not list(tmp_path.iterdir())


def test_rate_limit_tem_codigo_retryable_e_nao_cria_artefato(tmp_path, monkeypatch):
    segredo = VALID_KEY

    def fake_urlopen(req, timeout=None):
        if req.full_url.endswith("/models"):
            return _Response(_models_response())
        raise urllib.error.HTTPError(
            req.full_url,
            429,
            "Too Many Requests",
            {},
            io.BytesIO(f"rate limit token={segredo}".encode()),
        )

    monkeypatch.setattr(image.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(image.ImageLimitError) as exc:
        image.generate_image(_request(tmp_path, retries=0), segredo)

    assert exc.value.code == "rate_limit"
    assert exc.value.retryable
    assert segredo not in str(exc.value)
    assert segredo not in json.dumps(image.error_payload(exc.value, "pedido-1"))
    assert not list(tmp_path.iterdir())


def test_url_de_saida_expirada_e_sanitizada_sem_artefato(tmp_path, monkeypatch):
    url_expirada = (
        "https://storage.example/imagem.png?X-Amz-Expires=1&"
        "X-Amz-Signature=nao-exibir"
    )
    chamadas = []

    def fake_urlopen(req, timeout=None):
        chamadas.append(req)
        if req.full_url.endswith("/models"):
            return _Response(_models_response())
        if req.full_url == image.IMAGE_API_URL:
            return _Response(
                {"data": [{"url": url_expirada, "media_type": "image/png"}]}
            )
        raise urllib.error.HTTPError(
            req.full_url,
            403,
            "Forbidden",
            {},
            io.BytesIO(b"Request has expired"),
        )

    monkeypatch.setattr(image.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(image.ImageNetworkError) as exc:
        image.generate_image(_request(tmp_path, retries=0), VALID_KEY)

    assert exc.value.code == "network_error"
    assert url_expirada not in str(exc.value)
    assert url_expirada not in json.dumps(image.error_payload(exc.value, "pedido-1"))
    assert "Authorization" not in str(chamadas[-1].headers)
    assert not list(tmp_path.iterdir())


def test_chave_ausente_e_rejeitada_sem_chamada(tmp_path, monkeypatch):
    monkeypatch.setattr(
        image.urllib.request, "urlopen", lambda *a, **k: pytest.fail("não chamar")
    )

    with pytest.raises(image.ImageAuthenticationError) as exc:
        image.generate_image(_request(tmp_path), None)

    assert exc.value.code == "missing_key"


def test_falha_de_rede_tem_codigo_seguro(tmp_path, monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("segredo interno não deve aparecer")

    monkeypatch.setattr(image.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(image.ImageNetworkError) as exc:
        image.generate_image(_request(tmp_path, retries=0), VALID_KEY)

    assert exc.value.code == "network_error"
    assert "segredo interno" not in str(exc.value)


def test_mime_fora_da_allowlist_nao_cria_arquivo(tmp_path, monkeypatch):
    def fake_urlopen(req, timeout=None):
        if req.full_url.endswith("/models"):
            return _Response(_models_response())
        return _Response(
            {
                "data": [{"b64_json": PNG_B64, "media_type": "image/gif"}],
            }
        )

    monkeypatch.setattr(image.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(image.ImageFormatError) as exc:
        image.generate_image(_request(tmp_path), VALID_KEY)

    assert exc.value.code == "unsupported_mime"
    assert not list(tmp_path.iterdir())


def test_tamanho_excedido_limpa_saidas_anteriores(tmp_path, monkeypatch):
    segunda = b"\x89PNG\r\n\x1a\nsegunda-maior-e-bem-maior"
    respostas = iter(
        [
            _Response(_models_response()),
            _Response(
                {
                    "data": [
                        {"b64_json": PNG_B64, "media_type": "image/png"},
                        {
                            "b64_json": base64.b64encode(segunda).decode("ascii"),
                            "media_type": "image/png",
                        },
                    ]
                }
            ),
        ]
    )
    monkeypatch.setattr(
        image.urllib.request, "urlopen", lambda *a, **k: next(respostas)
    )
    monkeypatch.setattr(image, "MAX_OUTPUT_BYTES", len(PNG) + 1)

    with pytest.raises(image.ImageLimitError) as exc:
        image.generate_image(_request(tmp_path, count=2), VALID_KEY)

    assert exc.value.code == "output_too_large"
    assert not list(tmp_path.iterdir())


def test_timeout_retorna_erro_seguro_e_reenvia_mesma_chave(tmp_path, monkeypatch):
    chamadas_post = []
    tentativas = 0

    def fake_urlopen(req, timeout=None):
        nonlocal tentativas
        if req.full_url.endswith("/models"):
            return _Response(_models_response())
        chamadas_post.append(req.headers["Idempotency-key"])
        tentativas += 1
        if tentativas == 1:
            raise TimeoutError("não deve sair")
        return _Response({"data": [{"b64_json": PNG_B64}]})

    monkeypatch.setattr(image.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(image.time, "sleep", lambda segundos: None)

    resultado = image.generate_image(_request(tmp_path, retries=1), VALID_KEY)

    assert resultado.outputs[0].bytes == len(PNG)
    assert chamadas_post == ["pedido-1", "pedido-1"]


def test_cancelamento_nao_chama_api_nem_deixa_temporario(tmp_path, monkeypatch):
    evento = threading.Event()
    evento.set()
    monkeypatch.setattr(
        image.urllib.request, "urlopen", lambda *a, **k: pytest.fail("não chamar")
    )

    with pytest.raises(image.ImageCancelledError) as exc:
        image.generate_image(_request(tmp_path), VALID_KEY, cancel_event=evento)

    assert exc.value.code == "cancelled"
    assert not list(tmp_path.iterdir())


def test_chave_nunca_aparece_no_erro_http(tmp_path, monkeypatch):
    segredo = VALID_KEY

    def fake_urlopen(req, timeout=None):
        if req.full_url.endswith("/models"):
            raise urllib.error.HTTPError(
                req.full_url,
                401,
                "Unauthorized",
                {},
                io.BytesIO(f"token={segredo}".encode()),
            )
        pytest.fail("não deve chegar ao POST")

    monkeypatch.setattr(image.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(image.ImageAuthenticationError) as exc:
        image.generate_image(_request(tmp_path), segredo)

    assert segredo not in str(exc.value)
    assert segredo not in json.dumps(exc.value.to_dict())


def test_idempotencia_reutiliza_saida_existente_sem_nova_chamada(tmp_path, monkeypatch):
    caminho = tmp_path / "openia-image-pedido-1-1.png"
    caminho.write_bytes(PNG)
    monkeypatch.setattr(
        image.urllib.request, "urlopen", lambda *a, **k: pytest.fail("não chamar")
    )

    resultado = image.generate_image(_request(tmp_path), VALID_KEY)

    assert resultado.outputs[0].path == caminho.resolve()
    assert resultado.outputs[0].mime == "image/png"


def test_referencia_invalida_nao_permite_traversal_ou_mime_arbitrario(tmp_path):
    with pytest.raises(image.ImageValidationError):
        image.generate_image(
            _request(tmp_path, idempotency_key="../segredo"),
            VALID_KEY,
        )

    with pytest.raises(image.ImageValidationError):
        image._build_payload(
            _request(tmp_path, references=("data:text/html;base64,YQ==",))
        )
