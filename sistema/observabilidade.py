"""
sistema/observabilidade.py

Camada mínima de observabilidade do FIIA.
Registra eventos estruturados em JSON Lines para auditoria operacional.

Objetivo:
- impedir falhas silenciosas;
- identificar fonte/módulo/ticker afetado;
- preservar rastreabilidade sem depender de infraestrutura externa;
- permitir métricas técnicas de performance em formato estruturado.
"""
from __future__ import annotations

import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_RAIZ = Path(__file__).parent.parent
LOG_DIR = _RAIZ / "logs"
LOG_PATH = LOG_DIR / "fiia_eventos.jsonl"
_OBSERVABILIDADE_ATIVA = os.environ.get("FIIA_OBSERVABILIDADE", "1").lower() not in {"0", "false", "off", "no"}


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def configurar_observabilidade(ativa: bool) -> None:
    """
    Liga/desliga escrita de observabilidade em tempo de execução.

    Útil para testes de isolamento que bloqueiam I/O em disco. Quando desligada,
    registrar_evento, registrar_erro e registrar_metrica_performance viram no-op.
    """
    global _OBSERVABILIDADE_ATIVA
    _OBSERVABILIDADE_ATIVA = bool(ativa)


def observabilidade_ativa() -> bool:
    return _OBSERVABILIDADE_ATIVA


def _escrever_evento(evento: dict[str, Any]) -> None:
    if not _OBSERVABILIDADE_ATIVA:
        return

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as arquivo:
            arquivo.write(json.dumps(evento, ensure_ascii=False, default=str, sort_keys=True) + "\n")
    except Exception:
        # Observabilidade nunca deve quebrar fluxo decisório, radar ou testes.
        return


def registrar_evento(
    nivel: str,
    modulo: str,
    mensagem: str,
    *,
    ticker: str | None = None,
    fonte: str | None = None,
    contexto: dict[str, Any] | None = None,
) -> None:
    """Registra um evento operacional em formato JSON Lines estruturado."""
    evento = {
        "timestamp": _agora_iso(),
        "nivel": nivel.upper(),
        "modulo": modulo,
        "mensagem": mensagem,
        "ticker": ticker,
        "fonte": fonte,
        "contexto": contexto or {},
    }
    _escrever_evento(evento)


def registrar_metrica_performance(
    modulo: str,
    nome: str,
    metricas: dict[str, Any],
    *,
    ticker: str | None = None,
    fonte: str | None = None,
) -> None:
    """
    Registra métricas técnicas de performance em JSON estruturado.

    Exemplos de métricas esperadas: tempo_coleta_ms, tempo_decisao_ms,
    ativos_bloqueados, cache_hits, cache_misses e falhas_por_fonte.
    """
    registrar_evento(
        "METRIC",
        modulo,
        nome,
        ticker=ticker,
        fonte=fonte,
        contexto={
            "categoria": "performance",
            "metricas": metricas or {},
        },
    )


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