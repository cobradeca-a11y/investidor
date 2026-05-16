"""
sistema/autoupdater.py
Verifica se bibliotecas críticas estão desatualizadas, mas NÃO atualiza
automaticamente em produção.

Motivo:
- yfinance/fundamentus podem mudar contratos de retorno entre versões;
- upgrade silencioso pode quebrar coleta sem rastreabilidade;
- atualização deve ser decisão operacional testada, não efeito colateral do startup.
"""
from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

from sistema import observabilidade

# Bibliotecas que mudam com frequência e afetam a coleta
LIBS_CRITICAS = ["yfinance", "fundamentus"]


def _executar_pip_list_outdated() -> list[dict[str, Any]]:
    try:
        resultado = subprocess.run(
            [sys.executable, "-m", "pip", "list", "--outdated", "--format=json"],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(resultado.stdout)
    except Exception as e:
        observabilidade.registrar_erro(
            "sistema.autoupdater",
            e,
            contexto={"acao": "pip list --outdated"},
        )
        print(f"[autoupdater] Aviso: falha ao checar pacotes desatualizados via pip: {e}")
        return []


def bibliotecas_criticas_desatualizadas() -> list[dict[str, str]]:
    """Retorna bibliotecas críticas desatualizadas sem modificar o ambiente."""
    outdated = _executar_pip_list_outdated()
    libs: list[dict[str, str]] = []

    for lib in outdated:
        nome = lib.get("name", "")
        if nome in LIBS_CRITICAS:
            libs.append({
                "name": nome,
                "version": lib.get("version", "desconhecida"),
                "latest_version": lib.get("latest_version", "desconhecida"),
                "latest_filetype": lib.get("latest_filetype", "desconhecido"),
            })

    return libs


def verificar_e_atualizar() -> None:
    """
    Compatibilidade com chamadas antigas.

    O nome da função foi mantido para não quebrar imports existentes, mas o
    comportamento foi invertido: agora apenas verifica e alerta. Não executa
    `pip install --upgrade` automaticamente.
    """
    libs = bibliotecas_criticas_desatualizadas()

    if not libs:
        print("[autoupdater] Bibliotecas críticas sem atualização pendente.")
        return

    observabilidade.registrar_evento(
        "WARNING",
        "sistema.autoupdater",
        "Bibliotecas críticas desatualizadas — atualização manual recomendada após teste.",
        contexto={"bibliotecas": libs, "auto_update": False},
    )

    print("\n[autoupdater] Bibliotecas críticas desatualizadas detectadas.")
    print("Atualização automática BLOQUEADA por segurança operacional.")
    print("Teste as versões novas antes de atualizar o ambiente de produção.")
    print("-" * 50)
    print("  RELATÓRIO DE MANUTENÇÃO (Auto-Updater Seguro)")
    print("-" * 50)
    for lib in libs:
        print(f"  • {lib['name']}: v{lib['version']} → v{lib['latest_version']}")
    print("-" * 50 + "\n")


# Alias semântico para novas chamadas.
def verificar_bibliotecas() -> list[dict[str, str]]:
    """API explícita para auditoria/endpoint: verifica e retorna pendências."""
    return bibliotecas_criticas_desatualizadas()
