"""
sistema/observabilidade.py

Camada mínima de observabilidade do FIIA.
Registra eventos estruturados em JSON Lines para auditoria operacional.

Objetivo:
- impedir falhas silenciosas;
- identificar fonte/módulo/ticker afetado;
- preservar rastreabilidade sem depender de infraestrutura externa.
"""
from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_RAIZ = Path(__file__).parent.parent
LOG_DIR = _RAIZ / "logs"
LOG_PATH = LOG_DIR / "fiia_eventos.jsonl"


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def registrar_evento(
    nivel: str,
    modulo: str,
    mensagem: str,
    *,
    ticker: str | None = None,
    fonte: str | None = None,
    contexto: dict[str, Any] | None = None,
) -> None:
    """Registra um evento operacional em formato JSON Lines."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    evento = {
        "timestamp": _agora_iso(),
        "nivel": nivel.upper(),
        "modulo": modulo,
        "mensagem": mensagem,
        "ticker": ticker,
        "fonte": fonte,
        "contexto": contexto or {},
    }

    with LOG_PATH.open("a", encoding="utf-8") as arquivo:
        arquivo.write(json.dumps(evento, ensure_ascii=False, default=str) + "\n")


def registrar_erro(
    modulo: str,
    erro: Exception,
    *,
    ticker: str | None = None,
    fonte: str | None = None,
    contexto: dict[str, Any] | None = None,
) -> None:
    """Registra exceção com traceback para diagnóstico posterior."""
    contexto_final = dict(contexto or {})
    contexto_final.update(
        {
            "tipo_erro": type(erro).__name__,
            "erro": str(erro),
            "traceback": traceback.format_exc(),
        }
    )
    registrar_evento(
        "ERROR",
        modulo,
        str(erro),
        ticker=ticker,
        fonte=fonte,
        contexto=contexto_final,
    )
