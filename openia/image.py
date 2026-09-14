"""Geração de imagens via a Image API do OpenRouter.

Este módulo é deliberadamente separado do launcher textual. A fronteira pública
é pequena: ``ImageRequest`` descreve uma operação, ``generate_image`` executa a
chamada autenticada e ``ImageResult`` representa somente metadados do artefato
gravado. Nenhuma resposta crua do provedor ou segredo chega ao contrato JSON.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import socket
import tempfile
import threading
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__, config

IMAGE_API_URL = "https://openrouter.ai/api/v1/images"
IMAGE_MODELS_URL = "https://openrouter.ai/api/v1/images/models"
SCHEMA_VERSION = 1

DEFAULT_TIMEOUT = 120.0
DEFAULT_RETRIES = 2
MAX_OUTPUTS = 10
MAX_PROMPT_CHARS = 20_000
MAX_REFERENCE_COUNT = 10
MAX_REFERENCE_BYTES = 25 * 1024 * 1024
MAX_OUTPUT_BYTES = 25 * 1024 * 1024
MAX_RESPONSE_BYTES = 64 * 1024 * 1024
MAX_REQUEST_BYTES = 64 * 1024 * 1024

_ALLOWED_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
}
_FORMAT_TO_MIME = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "webp": "image/webp",
    "svg": "image/svg+xml",
}
_ALLOWED_QUALITY = {"auto", "low", "medium", "high"}
_ALLOWED_BACKGROUND = {"auto", "transparent", "opaque"}
_ALLOWED_RESOLUTIONS = {"512", "1K", "2K", "4K"}
_SAFE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SAFE_PROVIDER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SAFE_MODEL = re.compile(r"^[^/\s]+/[^/\s]+$")
_ASPECT_RATIO = re.compile(r"^(?:auto|[1-9][0-9]{0,2}:[1-9][0-9]{0,2})$")
_PIXEL_SIZE = re.compile(r"^([0-9]{2,5})x([0-9]{2,5})$")
_SVG_DANGEROUS = re.compile(
    rb"<(?:script\b|[^>]*\bon[a-z][a-z0-9_-]*\s*=)|"
    rb"(?:href|xlink:href)\s*=\s*['\"](?:https?:|//|javascript:)",
    re.IGNORECASE,
)


class ImageError(RuntimeError):
    """Erro público e seguro da operação de imagem."""

    code = "image_error"
    exit_code = 1
    retryable = False

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        self.code = code or self.code
        if retryable is not None:
            self.retryable = retryable
        self.message = message or "não foi possível concluir a geração de imagem."
        super().__init__(self.message)

    def to_dict(self) -> dict[str, object]:
        """Serializa apenas o código e a mensagem pública controlada."""
        return {
            "code": self.code,
            "message": self.message,
        }


class ImageValidationError(ImageError):
    """Entrada local inválida, sem chamada ao provedor."""

    code = "invalid_request"
    exit_code = 2


class ImageAuthenticationError(ImageError):
    """Chave ausente, malformada ou rejeitada pelo OpenRouter."""

    code = "authentication_error"
    exit_code = 3


class ImageModelError(ImageError):
    """Modelo ausente ou sem a capability necessária."""

    code = "model_error"
    exit_code = 4


class ImageLimitError(ImageError):
    """Limite local, de tamanho, saldo ou taxa do provedor."""

    code = "limit_error"
    exit_code = 5
    retryable = False


class ImageNetworkError(ImageError):
    """Falha de conexão com o OpenRouter ou com uma URL de saída."""

    code = "network_error"
    exit_code = 6
    retryable = True


class ImageTimeoutError(ImageError):
    """Tempo limite esgotado."""

    code = "timeout"
    exit_code = 124
    retryable = True


class ImageProviderError(ImageError):
    """Falha segura devolvida pelo endpoint/provedor escolhido."""

    code = "provider_error"
    exit_code = 7
    retryable = False


class ImageFormatError(ImageProviderError):
    """Saída que não é um formato de imagem permitido ou coerente."""

    code = "unsupported_mime"


class ImageStorageError(ImageError):
    """Falha ao criar o artefato localmente."""

    code = "output_error"
    exit_code = 8


class ImageCancelledError(ImageError):
    """Operação cancelada pelo host ou pelo usuário."""

    code = "cancelled"
    exit_code = 130


@dataclass(frozen=True)
class ImageRequest:
    """Dados validados de uma operação de geração.

    ``references`` aceita URLs HTTPS e data URLs/base64 de PNG, JPEG ou WebP.
    Caminhos de arquivo não são aceitos para evitar que uma entrada de CLI leia
    arquivos arbitrários do host.
    """

    model: str
    prompt: str
    output_dir: Path
    count: int = 1
    output_format: str | None = None
    resolution: str | None = None
    aspect_ratio: str | None = None
    size: str | None = None
    quality: str | None = None
    background: str | None = None
    output_compression: int | None = None
    seed: int | None = None
    references: tuple[str, ...] = ()
    provider: str | None = None
    timeout: float = DEFAULT_TIMEOUT
    retries: int = DEFAULT_RETRIES
    idempotency_key: str | None = None
    max_output_bytes: int | None = None


@dataclass(frozen=True)
class ImageModel:
    """Capability pública de um modelo retornada pelo endpoint de descoberta."""

    id: str
    output_modalities: tuple[str, ...]
    input_modalities: tuple[str, ...]
    supported_parameters: Mapping[str, object]


@dataclass(frozen=True)
class ImageOutput:
    """Um artefato final gravado no diretório do host."""

    path: Path
    mime: str
    bytes: int

    def to_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "mime": self.mime,
            "bytes": self.bytes,
        }


@dataclass(frozen=True)
class ImageResult:
    """Resposta versionada sem conteúdo binário nem dados de autenticação."""

    request_id: str
    model: str
    outputs: tuple[ImageOutput, ...]
    created_at: str
    completed_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "version": SCHEMA_VERSION,
            "ok": True,
            "requestId": self.request_id,
            "model": self.model,
            "outputs": [output.to_dict() for output in self.outputs],
            "createdAt": self.created_at,
            "completedAt": self.completed_at,
        }


CancelChecker = Callable[[], bool]
Urlopen = Callable[..., Any]


def _now() -> str:
    """Retorna timestamp UTC estável para o contrato JSON."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _check_cancel(
    cancel_event: threading.Event | None,
    cancel_checker: CancelChecker | None,
) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise ImageCancelledError("a operação foi cancelada.")
    if cancel_checker is not None:
        try:
            cancelado = cancel_checker()
        except OSError:
            cancelado = False
        if cancelado:
            raise ImageCancelledError("a operação foi cancelada.")


def _validate_api_key(api_key: str | None) -> str:
    if not api_key or not api_key.strip():
        raise ImageAuthenticationError(
            "nenhuma chave do OpenRouter foi configurada.", code="missing_key"
        )
    try:
        return config.validate_api_key(api_key)
    except ValueError:
        raise ImageAuthenticationError(
            "a chave do OpenRouter tem formato inválido.", code="invalid_key"
        ) from None


def _normalise_mime(value: str | None) -> str | None:
    if not value:
        return None
    mime = value.split(";", 1)[0].strip().lower()
    if mime == "image/jpg":
        mime = "image/jpeg"
    return mime


def _optional_text(value: object, nome: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ImageValidationError(f"{nome} deve ser texto não vazio.")
    return value.strip()


def _detect_mime(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    inicio = data.lstrip(b"\xef\xbb\xbf\x09\x0a\x0d\x20")[:2048].lower()
    if b"<svg" in inicio and b">" in inicio:
        return "image/svg+xml"
    return None


def _validate_svg(data: bytes) -> None:
    if _SVG_DANGEROUS.search(data):
        raise ImageFormatError(
            "a saída SVG contém conteúdo ativo não permitido.",
            code="unsafe_output",
        )


def _decode_base64(
    value: str,
    *,
    max_bytes: int,
    too_large_error: type[ImageError] = ImageValidationError,
    too_large_code: str | None = None,
) -> bytes:
    compact = re.sub(r"\s+", "", value)
    if not compact or len(compact) > ((max_bytes + 2) // 3) * 4 + 4:
        raise too_large_error(
            "o conteúdo base64 excede o limite permitido.", code=too_large_code
        )
    try:
        decoded = base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError):
        raise ImageValidationError("a referência base64 é inválida.") from None
    if not decoded or len(decoded) > max_bytes:
        raise too_large_error(
            "o conteúdo base64 excede o limite permitido.", code=too_large_code
        )
    return decoded


def _data_url_to_bytes(
    value: str,
    *,
    allowed_mimes: set[str] | frozenset[str] | None = None,
    max_bytes: int = MAX_REFERENCE_BYTES,
    too_large_error: type[ImageError] = ImageValidationError,
    too_large_code: str | None = None,
) -> tuple[bytes, str]:
    header, separator, encoded = value.partition(",")
    if separator != "," or not header.lower().startswith("data:"):
        raise ImageValidationError("a data URL da referência é inválida.")
    partes = header[5:].split(";")
    if len(partes) != 2 or partes[1].lower() != "base64":
        raise ImageValidationError("a referência deve usar base64.")
    mime = _normalise_mime(partes[0])
    permitidos = allowed_mimes or {"image/png", "image/jpeg", "image/webp"}
    if mime not in permitidos:
        raise ImageValidationError("o MIME da referência não é permitido.")
    data = _decode_base64(
        encoded,
        max_bytes=max_bytes,
        too_large_error=too_large_error,
        too_large_code=too_large_code,
    )
    detectado = _detect_mime(data)
    if detectado != mime:
        raise ImageValidationError("o conteúdo da referência não corresponde ao MIME.")
    return data, mime


def _validate_http_url(value: str) -> str:
    try:
        parsed = urllib.parse.urlparse(value)
        hostname = parsed.hostname
    except ValueError:
        hostname = None
        parsed = None
    if (
        parsed is None
        or parsed.scheme.lower() not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or any(ord(caractere) < 0x20 for caractere in value)
        or len(value) > 4096
    ):
        raise ImageValidationError("a referência deve ser uma URL HTTP(S) válida.")
    return value


def _normalise_reference(value: str) -> str:
    if not isinstance(value, str):
        raise ImageValidationError("a referência de imagem deve ser texto.")
    reference = value.strip()
    if not reference:
        raise ImageValidationError("a referência de imagem não pode ser vazia.")
    if reference.lower().startswith("data:"):
        data, mime = _data_url_to_bytes(reference)
        return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    parsed = urllib.parse.urlparse(reference)
    if parsed.scheme:
        if parsed.scheme.lower() != "https" and parsed.scheme.lower() != "http":
            raise ImageValidationError("a referência usa um esquema não permitido.")
        return _validate_http_url(reference)

    data = _decode_base64(reference, max_bytes=MAX_REFERENCE_BYTES)
    mime = _detect_mime(data)
    if mime not in {"image/png", "image/jpeg", "image/webp"}:
        raise ImageValidationError("a referência base64 não é uma imagem permitida.")
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _validate_request(request: ImageRequest) -> ImageRequest:
    model = request.model.strip() if isinstance(request.model, str) else ""
    if (
        not model
        or len(model) > 255
        or not _SAFE_MODEL.fullmatch(model)
        or ".." in model
    ):
        raise ImageValidationError("o modelo deve usar o formato empresa/modelo.")

    prompt = request.prompt.strip() if isinstance(request.prompt, str) else ""
    if not prompt:
        raise ImageValidationError("o prompt não pode ser vazio.")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise ImageValidationError("o prompt excede o limite permitido.")

    try:
        output_dir = Path(request.output_dir).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, TypeError):
        raise ImageValidationError("o diretório de saída não é válido.") from None
    if not output_dir.is_dir():
        raise ImageValidationError("o diretório de saída não é uma pasta.")

    if isinstance(request.count, bool) or not isinstance(request.count, int):
        raise ImageValidationError("a quantidade de imagens deve ser um inteiro.")
    if not 1 <= request.count <= MAX_OUTPUTS:
        raise ImageValidationError(
            f"a quantidade de imagens deve ficar entre 1 e {MAX_OUTPUTS}."
        )

    formato_raw = _optional_text(request.output_format, "o formato de saída")
    formato = formato_raw.lower().lstrip(".") if formato_raw else None
    if formato and formato not in _FORMAT_TO_MIME:
        raise ImageValidationError(
            "o formato de saída deve ser png, jpeg, webp ou svg."
        )
    if formato == "jpg":
        formato = "jpeg"

    resolution = _optional_text(request.resolution, "a resolução")
    if resolution and resolution not in _ALLOWED_RESOLUTIONS:
        raise ImageValidationError("a resolução solicitada não é permitida.")

    aspect_ratio = _optional_text(request.aspect_ratio, "a proporção")
    if aspect_ratio and not _ASPECT_RATIO.fullmatch(aspect_ratio):
        raise ImageValidationError("a proporção deve seguir o formato 16:9 ou auto.")

    size = _optional_text(request.size, "o tamanho")
    if size:
        if size in _ALLOWED_RESOLUTIONS:
            pass
        else:
            match = _PIXEL_SIZE.fullmatch(size)
            if not match or any(not 64 <= int(part) <= 8192 for part in match.groups()):
                raise ImageValidationError(
                    "o tamanho deve ser uma resolução permitida ou pixels válidos."
                )

    quality = _optional_text(request.quality, "a qualidade")
    if quality and quality not in _ALLOWED_QUALITY:
        raise ImageValidationError("a qualidade deve ser auto, low, medium ou high.")
    background = _optional_text(request.background, "o fundo")
    if background and background not in _ALLOWED_BACKGROUND:
        raise ImageValidationError("o fundo deve ser auto, transparent ou opaque.")
    if background == "transparent" and formato not in {None, "png", "webp"}:
        raise ImageValidationError("fundo transparente exige PNG ou WebP.")

    if request.output_compression is not None and (
        isinstance(request.output_compression, bool)
        or not isinstance(request.output_compression, int)
        or not 0 <= request.output_compression <= 100
    ):
        raise ImageValidationError("a compressão deve ser um inteiro entre 0 e 100.")
    if request.seed is not None and (
        isinstance(request.seed, bool)
        or not isinstance(request.seed, int)
        or not -(2**63) <= request.seed <= 2**63 - 1
    ):
        raise ImageValidationError("a seed deve ser um inteiro válido.")

    provider = _optional_text(request.provider, "o provider")
    if provider and not _SAFE_PROVIDER.fullmatch(provider):
        raise ImageValidationError("o provider contém caracteres não permitidos.")
    if isinstance(request.timeout, bool) or not isinstance(
        request.timeout, (int, float)
    ):
        raise ImageValidationError("o timeout deve ser numérico.")
    if not 0.1 <= float(request.timeout) <= 600:
        raise ImageValidationError("o timeout deve ficar entre 0,1 e 600 segundos.")
    if isinstance(request.retries, bool) or not isinstance(request.retries, int):
        raise ImageValidationError("retries deve ser um inteiro.")
    if not 0 <= request.retries <= 5:
        raise ImageValidationError("retries deve ficar entre 0 e 5.")

    key = request.idempotency_key
    if key is not None and (not isinstance(key, str) or not _SAFE_KEY.fullmatch(key)):
        raise ImageValidationError(
            "a chave de idempotência contém caracteres não permitidos."
        )

    limite = (
        request.max_output_bytes
        if request.max_output_bytes is not None
        else MAX_OUTPUT_BYTES
    )
    if (
        isinstance(limite, bool)
        or not isinstance(limite, int)
        or not 1 <= limite <= MAX_OUTPUT_BYTES
    ):
        raise ImageValidationError("o limite de saída não é válido.")

    if request.references is None:
        referencias = ()
    elif isinstance(request.references, (str, bytes)):
        raise ImageValidationError("as referências devem ser uma coleção de textos.")
    else:
        try:
            referencias = tuple(request.references)
        except TypeError:
            raise ImageValidationError(
                "as referências devem ser uma coleção de textos."
            ) from None
    if len(referencias) > MAX_REFERENCE_COUNT:
        raise ImageValidationError(
            f"são permitidas no máximo {MAX_REFERENCE_COUNT} referências."
        )
    normalizadas = tuple(_normalise_reference(reference) for reference in referencias)

    return ImageRequest(
        model=model,
        prompt=prompt,
        output_dir=output_dir,
        count=request.count,
        output_format=formato,
        resolution=resolution,
        aspect_ratio=aspect_ratio,
        size=size,
        quality=quality,
        background=background,
        output_compression=request.output_compression,
        seed=request.seed,
        references=normalizadas,
        provider=provider,
        timeout=float(request.timeout),
        retries=request.retries,
        idempotency_key=key,
        max_output_bytes=limite,
    )


def _build_payload(request: ImageRequest) -> dict[str, object]:
    """Monta o payload permitido pela Image API, sem dados de autenticação."""
    request = _validate_request(request)
    payload: dict[str, object] = {
        "model": request.model,
        "prompt": request.prompt,
    }
    if request.count > 1:
        payload["n"] = request.count
    campos = {
        "resolution": request.resolution,
        "aspect_ratio": request.aspect_ratio,
        "size": request.size,
        "quality": request.quality,
        "output_format": request.output_format,
        "background": request.background,
        "output_compression": request.output_compression,
        "seed": request.seed,
    }
    payload.update({nome: valor for nome, valor in campos.items() if valor is not None})
    if request.references:
        payload["input_references"] = [
            {"type": "image_url", "image_url": {"url": reference}}
            for reference in request.references
        ]
    if request.provider:
        payload["provider"] = {
            "only": [request.provider],
            "allow_fallbacks": False,
        }
    try:
        request_size = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError):  # _validate_request já filtrou os tipos públicos.
        raise ImageValidationError(
            "a requisição de imagem não pôde ser serializada."
        ) from None
    if request_size > MAX_REQUEST_BYTES:
        raise ImageLimitError(
            "a requisição de imagem excede o limite de segurança.",
            code="request_too_large",
        )
    return payload


def _safe_body_hint(raw: bytes) -> str:
    """Extrai somente palavras de classificação; nunca é usado como mensagem."""
    return raw[:8192].decode("utf-8", errors="ignore").lower()


def _retry_delay(attempt: int) -> float:
    return min(2.0**attempt, 8.0)


def _read_limited(response: Any, limit: int) -> bytes:
    try:
        raw = response.read(limit + 1)
    except TypeError:
        # Alguns doubles simples de teste expõem apenas read().
        raw = response.read()
    if not raw:
        return b""
    if not isinstance(raw, bytes):
        raw = bytes(raw)
    if len(raw) > limit:
        raise ImageLimitError(
            "a resposta do provedor excede o limite de segurança.",
            code="response_too_large",
        )
    return raw


def _status(response: Any) -> int:
    valor = getattr(response, "status", None)
    if valor is None:
        valor = response.getcode() if hasattr(response, "getcode") else 200
    return int(valor or 200)


def _classify_http_error(
    status: int, phase: str, hint: str, *, provider_selected: bool = False
) -> ImageError:
    if status in {401, 403}:
        return ImageAuthenticationError(
            "a chave do OpenRouter foi rejeitada.", code="authentication_error"
        )
    if status == 402:
        return ImageLimitError(
            "a conta do OpenRouter não tem saldo ou limite disponível.",
            code="account_limit",
        )
    if status == 413:
        return ImageLimitError(
            "a requisição ou resposta excede o limite permitido.",
            code="request_too_large",
        )
    if status == 429:
        return ImageLimitError(
            "o limite de requisições do OpenRouter foi atingido.",
            code="rate_limit",
            retryable=True,
        )
    if status in {408, 504}:
        return ImageTimeoutError("o OpenRouter não respondeu dentro do prazo.")
    if status == 404:
        if phase == "models":
            return ImageProviderError(
                "o serviço de descoberta de modelos não está disponível.",
                code="provider_unavailable",
            )
        if provider_selected or "provider" in hint:
            return ImageProviderError(
                "o provider selecionado não suporta esta operação.",
                code="provider_unsupported",
            )
        return ImageModelError(
            "o modelo solicitado não foi encontrado.", code="model_not_found"
        )
    if status in {400, 422}:
        if any(marca in hint for marca in ("provider", "no endpoints", "endpoint")):
            return ImageProviderError(
                "o provider selecionado não suporta esta operação.",
                code="provider_unsupported",
            )
        if "model" in hint:
            return ImageModelError(
                "o modelo não aceita os parâmetros solicitados.",
                code="model_unsupported",
            )
        if any(marca in hint for marca in ("limit", "size", "payload")):
            return ImageLimitError(
                "a requisição excede um limite aceito pelo provedor.",
                code="request_limit",
            )
        return ImageValidationError("a requisição de imagem foi rejeitada.")
    if status in {500, 502, 503}:
        return ImageProviderError(
            "o provider de imagem está indisponível no momento.",
            code="provider_unavailable",
            retryable=True,
        )
    return ImageProviderError(
        "o serviço de imagem retornou uma falha controlada.", code="provider_error"
    )


def _request_json(
    url: str,
    *,
    api_key: str,
    payload: dict[str, object] | None,
    timeout: float,
    retries: int,
    phase: str,
    idempotency_key: str | None = None,
    provider_selected: bool = False,
    cancel_event: threading.Event | None = None,
    cancel_checker: CancelChecker | None = None,
    opener: Urlopen | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> dict[str, object]:
    """Faz uma chamada JSON com retry seguro e classificação sem corpo cru."""
    opener = opener or urllib.request.urlopen
    sleeper = sleeper or time.sleep
    body = None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": f"openia/{__version__}",
    }
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        headers["Content-Type"] = "application/json"
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key

    for tentativa in range(retries + 1):
        _check_cancel(cancel_event, cancel_checker)
        request = urllib.request.Request(
            url,
            data=body,
            headers=headers,
            method="POST" if body is not None else "GET",
        )
        try:
            with opener(request, timeout=timeout) as response:
                status = _status(response)
                raw = _read_limited(response, MAX_RESPONSE_BYTES)
                if not 200 <= status < 300:
                    erro = _classify_http_error(
                        status,
                        phase,
                        _safe_body_hint(raw),
                        provider_selected=provider_selected,
                    )
                    if erro.retryable and tentativa < retries:
                        _check_cancel(cancel_event, cancel_checker)
                        sleeper(_retry_delay(tentativa))
                        continue
                    raise erro
                try:
                    valor = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    raise ImageProviderError(
                        "o provider retornou uma resposta inválida.",
                        code="invalid_provider_response",
                    ) from None
                if not isinstance(valor, dict):
                    raise ImageProviderError(
                        "o provider retornou uma resposta inválida.",
                        code="invalid_provider_response",
                    )
                return valor
        except ImageError as exc:
            if exc.retryable and tentativa < retries:
                _check_cancel(cancel_event, cancel_checker)
                sleeper(_retry_delay(tentativa))
                continue
            raise
        except urllib.error.HTTPError as exc:
            try:
                hint = _safe_body_hint(exc.read(8192))
            except (OSError, TypeError):
                hint = ""
            erro = _classify_http_error(
                exc.code,
                phase,
                hint,
                provider_selected=provider_selected,
            )
            if erro.retryable and tentativa < retries:
                _check_cancel(cancel_event, cancel_checker)
                sleeper(_retry_delay(tentativa))
                continue
            raise erro from None
        except (socket.timeout, TimeoutError):
            erro = ImageTimeoutError("o OpenRouter não respondeu dentro do prazo.")
            if tentativa < retries:
                _check_cancel(cancel_event, cancel_checker)
                sleeper(_retry_delay(tentativa))
                continue
            raise erro from None
        except (urllib.error.URLError, OSError):
            erro = ImageNetworkError("não foi possível conectar ao OpenRouter.")
            if tentativa < retries:
                _check_cancel(cancel_event, cancel_checker)
                sleeper(_retry_delay(tentativa))
                continue
            raise erro from None

    raise ImageNetworkError(
        "não foi possível conectar ao OpenRouter."
    )  # pragma: no cover


def list_image_models(
    api_key: str | None,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    cancel_event: threading.Event | None = None,
    cancel_checker: CancelChecker | None = None,
    opener: Urlopen | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> tuple[ImageModel, ...]:
    """Consulta o catálogo de modelos que declaram saída de imagem."""
    chave = _validate_api_key(api_key)
    payload = _request_json(
        IMAGE_MODELS_URL,
        api_key=chave,
        payload=None,
        timeout=timeout,
        retries=retries,
        phase="models",
        cancel_event=cancel_event,
        cancel_checker=cancel_checker,
        opener=opener,
        sleeper=sleeper,
    )
    dados = payload.get("data")
    if not isinstance(dados, list):
        raise ImageProviderError(
            "o catálogo de imagens retornou um formato inválido.",
            code="invalid_model_catalog",
        )

    modelos: list[ImageModel] = []
    for item in dados:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id")
        if not isinstance(model_id, str) or not _SAFE_MODEL.fullmatch(model_id):
            continue
        architecture = item.get("architecture")
        if not isinstance(architecture, dict):
            architecture = {}
        output_modalities = architecture.get("output_modalities")
        input_modalities = architecture.get("input_modalities")
        supported = item.get("supported_parameters")
        modelos.append(
            ImageModel(
                id=model_id,
                output_modalities=tuple(
                    value for value in output_modalities if isinstance(value, str)
                )
                if isinstance(output_modalities, list)
                else (),
                input_modalities=tuple(
                    value for value in input_modalities if isinstance(value, str)
                )
                if isinstance(input_modalities, list)
                else (),
                supported_parameters=supported if isinstance(supported, dict) else {},
            )
        )
    return tuple(modelos)


def _validate_model_capabilities(
    request: ImageRequest, models: tuple[ImageModel, ...]
) -> None:
    encontrado = next((item for item in models if item.id == request.model), None)
    if encontrado is None:
        raise ImageModelError(
            "o modelo não foi encontrado no catálogo de imagens.",
            code="model_not_found",
        )
    if "image" not in encontrado.output_modalities:
        raise ImageModelError(
            "o modelo não declara saída de imagem.", code="model_unsupported"
        )
    if request.references and "image" not in encontrado.input_modalities:
        raise ImageModelError(
            "o modelo não aceita referências de imagem.", code="model_input_unsupported"
        )

    supported = encontrado.supported_parameters
    if not supported:
        return
    pedidos = {
        "n": request.count > 1,
        "output_format": request.output_format is not None,
        "resolution": request.resolution is not None,
        "aspect_ratio": request.aspect_ratio is not None,
        "size": request.size is not None,
        "quality": request.quality is not None,
        "background": request.background is not None,
        "output_compression": request.output_compression is not None,
        "seed": request.seed is not None,
        "input_references": bool(request.references),
    }
    for parametro, pedido in pedidos.items():
        if pedido and parametro not in supported:
            raise ImageModelError(
                f"o modelo não suporta o parâmetro de imagem solicitado: {parametro}.",
                code="unsupported_parameter",
            )


def _download_url(
    url: str,
    *,
    timeout: float,
    max_bytes: int,
    cancel_event: threading.Event | None,
    cancel_checker: CancelChecker | None,
    opener: Urlopen,
) -> tuple[bytes, str | None]:
    if url.lower().startswith("data:"):
        try:
            return _data_url_to_bytes(
                url,
                allowed_mimes=set(_ALLOWED_MIME),
                max_bytes=max_bytes,
                too_large_error=ImageLimitError,
                too_large_code="output_too_large",
            )
        except ImageLimitError:
            raise
        except ImageValidationError:
            raise ImageProviderError(
                "a URL de dados da saída é inválida.", code="invalid_output"
            ) from None
    try:
        url = _validate_http_url(url)
    except ImageValidationError:
        raise ImageProviderError(
            "a URL da imagem de saída é inválida.", code="invalid_output"
        ) from None
    _check_cancel(cancel_event, cancel_checker)
    request = urllib.request.Request(
        url, headers={"User-Agent": f"openia/{__version__}"}
    )
    try:
        with opener(request, timeout=timeout) as response:
            status = _status(response)
            if not 200 <= status < 300:
                raise ImageNetworkError("não foi possível obter a imagem de saída.")
            data = _read_limited(response, max_bytes)
            content_type = None
            if hasattr(response, "getheader"):
                content_type = response.getheader("Content-Type")
            if not content_type:
                headers = getattr(response, "headers", {})
                content_type = (
                    headers.get("Content-Type") if hasattr(headers, "get") else None
                )
            return data, _normalise_mime(content_type)
    except ImageError:
        raise
    except urllib.error.HTTPError:
        raise ImageNetworkError("não foi possível obter a imagem de saída.") from None
    except (socket.timeout, TimeoutError):
        raise ImageTimeoutError(
            "o download da imagem de saída excedeu o prazo."
        ) from None
    except (urllib.error.URLError, OSError):
        raise ImageNetworkError("não foi possível obter a imagem de saída.") from None


def _materialize_image(
    item: object,
    *,
    timeout: float,
    max_bytes: int,
    cancel_event: threading.Event | None,
    cancel_checker: CancelChecker | None,
    opener: Urlopen,
) -> tuple[bytes, str]:
    if not isinstance(item, dict):
        raise ImageProviderError(
            "o provider retornou uma saída inválida.", code="invalid_output"
        )
    declared_value = item.get("media_type") or item.get("mime_type") or item.get("mime")
    declared = _normalise_mime(
        declared_value if isinstance(declared_value, str) else None
    )
    data: bytes
    if isinstance(item.get("b64_json"), str):
        encoded = item["b64_json"]
        if encoded.lower().startswith("data:"):
            try:
                data, url_mime = _data_url_to_bytes(
                    encoded,
                    allowed_mimes=set(_ALLOWED_MIME),
                    max_bytes=max_bytes,
                    too_large_error=ImageLimitError,
                    too_large_code="output_too_large",
                )
            except ImageLimitError:
                raise
            except ImageValidationError:
                raise ImageProviderError(
                    "o provider retornou uma data URL inválida.", code="invalid_output"
                ) from None
            declared = declared or url_mime
        else:
            try:
                data = _decode_base64(
                    encoded,
                    max_bytes=max_bytes,
                    too_large_error=ImageLimitError,
                    too_large_code="output_too_large",
                )
            except ImageLimitError:
                raise
            except ImageValidationError:
                raise ImageProviderError(
                    "o provider retornou base64 inválido.", code="invalid_output"
                ) from None
    else:
        url = item.get("url")
        if not isinstance(url, str):
            image_url = item.get("image_url")
            if isinstance(image_url, dict):
                url = image_url.get("url")
        if not isinstance(url, str):
            raise ImageProviderError(
                "o provider não retornou um artefato de imagem.", code="missing_output"
            )
        data, downloaded_mime = _download_url(
            url,
            timeout=timeout,
            max_bytes=max_bytes,
            cancel_event=cancel_event,
            cancel_checker=cancel_checker,
            opener=opener,
        )
        declared = declared or downloaded_mime

    if len(data) > max_bytes:
        raise ImageLimitError(
            "o artefato excede o tamanho máximo permitido.", code="output_too_large"
        )
    detected = _detect_mime(data)
    if declared and declared not in _ALLOWED_MIME:
        raise ImageFormatError("o MIME retornado pelo provider não é permitido.")
    if detected is None:
        raise ImageFormatError(
            "o conteúdo retornado não é uma imagem permitida.", code="invalid_output"
        )
    if declared and detected != declared:
        raise ImageFormatError(
            "o MIME não corresponde ao conteúdo retornado.", code="mime_mismatch"
        )
    if detected == "image/svg+xml":
        _validate_svg(data)
    return data, detected


def _output_path(request: ImageRequest, index: int, mime: str) -> Path:
    # A chave foi validada por _validate_request; logo não pode introduzir
    # separadores de caminho ou caracteres de controle no nome final.
    key = request.idempotency_key or "sem-chave"
    return request.output_dir / f"openia-image-{key}-{index + 1}{_ALLOWED_MIME[mime]}"


def _read_existing(path: Path, limit: int) -> ImageOutput | None:
    try:
        if not path.is_file() or path.is_symlink() or path.stat().st_size > limit:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    mime = _detect_mime(data)
    if mime not in _ALLOWED_MIME:
        return None
    if mime == "image/svg+xml":
        try:
            _validate_svg(data)
        except ImageFormatError:
            return None
    return ImageOutput(path=path.resolve(), mime=mime, bytes=len(data))


def _existing_outputs(request: ImageRequest) -> tuple[ImageOutput, ...] | None:
    outputs: list[ImageOutput] = []
    try:
        entradas = tuple(request.output_dir.iterdir())
    except OSError:
        raise ImageStorageError(
            "não foi possível acessar o diretório de saída."
        ) from None
    for index in range(request.count):
        prefix = f"openia-image-{request.idempotency_key}-{index + 1}."
        candidatos = [
            path
            for path in entradas
            if path.name.startswith(prefix)
            and path.suffix.lower() in _ALLOWED_MIME.values()
        ]
        if not candidatos:
            return None
        existente = _read_existing(
            candidatos[0], request.max_output_bytes or MAX_OUTPUT_BYTES
        )
        if existente is None:
            return None
        outputs.append(existente)
    return tuple(outputs)


def _atomic_write(path: Path, data: bytes) -> None:
    temporary: str | None = None
    try:
        fd, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
        )
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError:
        raise ImageStorageError(
            "não foi possível gravar o artefato no diretório de saída."
        ) from None
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _cleanup(paths: list[Path]) -> None:
    for path in paths:
        try:
            if path.is_file() or path.is_symlink():
                path.unlink()
        except OSError:
            pass


def generate_image(
    request: ImageRequest,
    api_key: str | None,
    *,
    cancel_event: threading.Event | None = None,
    cancel_checker: CancelChecker | None = None,
    opener: Urlopen | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> ImageResult:
    """Gera, valida e grava imagens; falhas nunca deixam arquivo parcial."""
    request = _validate_request(request)
    request_id = request.idempotency_key or uuid.uuid4().hex
    request = replace(request, idempotency_key=request_id)
    _check_cancel(cancel_event, cancel_checker)
    chave = _validate_api_key(api_key)
    iniciado = _now()
    escritos: list[Path] = []
    opener = opener or urllib.request.urlopen
    try:
        existentes = _existing_outputs(request)
        if existentes is not None:
            return ImageResult(
                request_id=request_id,
                model=request.model,
                outputs=existentes,
                created_at=iniciado,
                completed_at=_now(),
            )

        modelos = list_image_models(
            chave,
            timeout=request.timeout,
            retries=request.retries,
            cancel_event=cancel_event,
            cancel_checker=cancel_checker,
            opener=opener,
            sleeper=sleeper,
        )
        _validate_model_capabilities(request, modelos)
        payload = _build_payload(request)
        resposta = _request_json(
            IMAGE_API_URL,
            api_key=chave,
            payload=payload,
            timeout=request.timeout,
            retries=request.retries,
            phase="generate",
            idempotency_key=request_id,
            provider_selected=bool(request.provider),
            cancel_event=cancel_event,
            cancel_checker=cancel_checker,
            opener=opener,
            sleeper=sleeper,
        )
        dados = resposta.get("data")
        if not isinstance(dados, list) or not dados:
            raise ImageProviderError(
                "o provider não retornou imagens.", code="missing_output"
            )

        outputs: list[ImageOutput] = []
        for index, item in enumerate(dados[: request.count]):
            _check_cancel(cancel_event, cancel_checker)
            data, mime = _materialize_image(
                item,
                timeout=request.timeout,
                max_bytes=request.max_output_bytes or MAX_OUTPUT_BYTES,
                cancel_event=cancel_event,
                cancel_checker=cancel_checker,
                opener=opener,
            )
            if len(data) > (request.max_output_bytes or MAX_OUTPUT_BYTES):
                raise ImageLimitError(
                    "o artefato excede o tamanho máximo permitido.",
                    code="output_too_large",
                )
            if request.output_format and mime != _FORMAT_TO_MIME[request.output_format]:
                raise ImageFormatError(
                    "o provider não respeitou o formato solicitado.",
                    code="format_mismatch",
                )
            destino = _output_path(request, index, mime)
            existente = _read_existing(
                destino, request.max_output_bytes or MAX_OUTPUT_BYTES
            )
            if existente is not None:
                outputs.append(existente)
                continue
            _atomic_write(destino, data)
            escritos.append(destino)
            outputs.append(
                ImageOutput(path=destino.resolve(), mime=mime, bytes=len(data))
            )

        if not outputs:
            raise ImageProviderError(
                "o provider não retornou imagens utilizáveis.", code="invalid_output"
            )
        return ImageResult(
            request_id=request_id,
            model=request.model,
            outputs=tuple(outputs),
            created_at=iniciado,
            completed_at=_now(),
        )
    except KeyboardInterrupt:
        _cleanup(escritos)
        raise ImageCancelledError("a operação foi cancelada.") from None
    except ImageError:
        _cleanup(escritos)
        raise


def error_payload(
    error: ImageError, request_id: str | None = None
) -> dict[str, object]:
    """Cria o envelope JSON de erro do comando ``image``."""
    payload: dict[str, object] = {
        "version": SCHEMA_VERSION,
        "ok": False,
        "error": error.to_dict(),
    }
    if request_id and _SAFE_KEY.fullmatch(request_id):
        payload["requestId"] = request_id
    return payload
