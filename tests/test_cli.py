"""Testes da lógica de navegação do menu (sem terminal interativo real)."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from openia import cli
from openia import config, models
from openia.interfaces import registry

VALID_KEY = "sk-or-v1-" + "a" * 40


def test_version_is_available_for_external_launcher_detection():
    result = CliRunner().invoke(cli.app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "0.1.0"


def test_list_json_expoe_contrato_sanitizado_de_interfaces():
    result = CliRunner().invoke(cli.app, ["list", "--json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert [item["key"] for item in payload["interfaces"]] == [
        iface.key for iface in registry.all_interfaces()
    ]
    assert all("env_keys" not in item and "api_key" not in item for item in payload["interfaces"])
    openclaw = next(item for item in payload["interfaces"] if item["key"] == "openclaw")
    assert openclaw["supportsModelSelection"] is True


def test_models_json_expoe_apenas_campos_publicos(monkeypatch):
    monkeypatch.setattr(
        cli.models,
        "load_models",
        lambda force_refresh=False: [
            models.Model(
                id="anthropic/claude-sonnet-4",
                vendor="anthropic",
                name="Claude Sonnet 4",
                completion_price=0.000015,
            )
        ],
    )

    result = CliRunner().invoke(cli.app, ["models", "--json"])

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout) == {
        "models": [{
            "id": "anthropic/claude-sonnet-4",
            "vendor": "anthropic",
            "name": "Claude Sonnet 4",
            "completionPrice": 0.000015,
        }]
    }


def test_key_status_json_nao_revela_a_chave(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_KEYS_PATH", tmp_path / "keys.json")
    monkeypatch.setattr(config, "_LEGACY_ENV_PATH", tmp_path / ".env")
    monkeypatch.delenv(config.ENV_VAR, raising=False)
    config.add_key("felixo", VALID_KEY)

    result = CliRunner().invoke(cli.app, ["key", "status", "--json"])

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout) == {
        "configured": True,
        "active": "felixo",
        "storedKeys": 1,
    }
    assert VALID_KEY not in result.stdout


def test_key_set_stdin_grava_sem_colocar_segredo_no_argumento_ou_saida(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_KEYS_PATH", tmp_path / "keys.json")
    monkeypatch.setattr(config, "_LEGACY_ENV_PATH", tmp_path / ".env")
    monkeypatch.delenv(config.ENV_VAR, raising=False)

    result = CliRunner().invoke(
        cli.app,
        ["key", "set-stdin", "felixo", "--json"],
        input=f"{VALID_KEY}\n",
    )

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout) == {"ok": True, "configured": True}
    assert config.load_api_key() == VALID_KEY
    assert VALID_KEY not in result.stdout


def test_decide_mode_voltar_cancela(monkeypatch):
    """Escolher voltar (0) em 'como autenticar' deve cancelar, não avançar."""
    # _pick_from devolve None quando o usuário escolhe voltar.
    monkeypatch.setattr(cli, "_pick_from", lambda *a, **k: None)
    iface = registry.get("claudecode")  # suporta assinatura → faz a pergunta
    with pytest.raises(cli._Cancelado):
        cli._decide_mode(iface, subscription=False, provider=False)


def test_decide_mode_openrouter_e_assinatura(monkeypatch):
    iface = registry.get("claudecode")
    # idx 0 = OpenRouter (provider=True)
    monkeypatch.setattr(cli, "_pick_from", lambda *a, **k: 0)
    assert cli._decide_mode(iface, False, False) is True
    # idx 1 = assinatura (provider=False)
    monkeypatch.setattr(cli, "_pick_from", lambda *a, **k: 1)
    assert cli._decide_mode(iface, False, False) is False


def test_decide_mode_sem_assinatura_sempre_provider():
    """Interface que não suporta assinatura nunca pergunta: é sempre provider."""
    iface = registry.get("opencode")
    assert cli._decide_mode(iface, False, False) is True


def test_pick_from_zero_devolve_none(monkeypatch):
    """Escolher 0 (voltar) devolve None, nunca um índice."""
    monkeypatch.setattr(cli.ui, "ask_number", lambda *a, **k: 0)
    assert cli._pick_from("t", ["a", "b"]) is None


def test_pick_from_repete_ate_opcao_valida(monkeypatch):
    """Opção fora do intervalo repete o menu (em loop) até uma escolha válida."""
    respostas = iter([99, -1, 2])
    monkeypatch.setattr(cli.ui, "ask_number", lambda *a, **k: next(respostas))
    assert cli._pick_from("t", ["a", "b"]) == 1


def test_choose_workdir_zero_cancela(monkeypatch):
    """Digitar 0 no passo da pasta cancela e volta ao menu (bug: antes virava
    'a pasta não existe: 0' num loop sem saída)."""
    import typer

    monkeypatch.setattr(typer, "prompt", lambda *a, **k: "0")
    iface = registry.get("claudecode")
    with pytest.raises(cli._Cancelado):
        cli._choose_workdir(iface)


def test_relaunch_cmd_provider_com_modelo():
    """Relançamento no terminal novo vira `openia run` com flags explícitas —
    sem prompt repetido e sem segredo no comando."""
    iface = registry.get("claudecode")
    cmd = cli._relaunch_cmd(iface, use_provider=True, model_id="anthropic/x", cwd="/tmp/proj")
    assert cmd[1:] == ["-m", "openia", "run", "claudecode",
                       "--provider", "-m", "anthropic/x", "-C", "/tmp/proj"]
    assert not any("sk-" in parte for parte in cmd)  # nenhuma chave viaja por argumento


def test_relaunch_cmd_assinatura_sem_modelo():
    """Modo assinatura não passa modelo (não há provider); pasta ainda vai por -C."""
    iface = registry.get("claudecode")
    cmd = cli._relaunch_cmd(iface, use_provider=False, model_id=None, cwd="/tmp/proj")
    assert cmd[1:] == ["-m", "openia", "run", "claudecode", "--subscription", "-C", "/tmp/proj"]
