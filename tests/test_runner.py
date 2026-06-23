"""Testes do runner: o gate de consentimento para instaladores via script.

Não exercita instalação real (rede); valida a regra de segurança de que um
instalador SCRIPT só roda com consentimento explícito.
"""

from __future__ import annotations

import pytest

from orctl import runner
from orctl.interfaces.base import AIInterface, Ecosystem

SCRIPT_IFACE = AIInterface(
    key="exemplo_script",
    name="ExemploScript",
    description="teste",
    ecosystem=Ecosystem.SCRIPT,
    package="",
    command="exemplo_script",
    homepage="https://example.com",
    install_script="https://example.com/install",
)


def test_install_script_sem_consentimento_falha():
    with pytest.raises(runner.ToolingError) as exc:
        runner.install(SCRIPT_IFACE, allow_script=False)
    assert "script remoto" in str(exc.value)
