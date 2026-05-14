"""
aprendizado/avaliador.py
Avalia decisões passadas em duas janelas de tempo.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from banco import db
from coleta.api_bcb import obter_selic_atual, obter_cdi_atual
from sistema import observabilidade

_SQL_RESULTADO = """
CREATE TABLE IF NOT EXISTS decisoes_resultado (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    decisao_id          INTEGER NOT NULL,
    ticker              TEXT NOT NULL,
    janela_dias         INTEGER NOT NULL,
    data_avaliacao      TEXT NOT NULL,
    preco_entrada       REAL,
    preco_avaliacao     REAL,
    retorno_preco       REAL,
    retorno_dividendos  REAL,
    retorno_total       REAL,
    retorno_cdi_periodo REAL,
    fonte_benchmark     TEXT,
    acerto              INTEGER DEFAULT 0,
    tipo_resultado      TEXT,
    observacao          TEXT,
    criado_em           TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(decisao_id, janela_dias)
);
"""


def _garantir_tabela() -> None:
    db.executar(_SQL_RESULTADO)


def _row_get(row: Any, chave: str, padrao: Any = None) -> Any:
    try:
        return row[chave]
    except Exception:
        return padrao


def _benchmark_periodo(dias: int) -> tuple[float, str]:
    """Retorna benchmark equivalente ao CDI para o período."""
    fonte = "DESCONHECIDA"

    try:
        cdi_anual = obter_cdi_atual()
        if cdi_anual is not None:
            fonte = "CDI_BCB"
            valor = round((1 + cdi_anual / 100) ** (dias / 252) - 1, 4) * 100
            return valor, fonte
    except Exception as erro:
        observabilidade.registrar_erro(
            "aprendizado.avaliador",
            erro,
            fonte="BCB_CDI",
            contexto={"funcao": "_benchmark_periodo", "dias": dias},
        )

    try:
        selic_anual = obter_selic_atual()
        if selic_anual is not None:
            fonte = "SELIC_BCB"
            valor = round((1 + selic_anual / 100) ** (dias / 252) - 1, 4) * 100
            return valor, fonte
    except Exception as erro:
        observabilidade.registrar_erro(
            "aprendizado.avaliador",
            erro,
            fonte="BCB_SELIC",
            contexto={"funcao": "_benchmark_periodo", "dias": dias},
        )

    try:
        row = db.buscar_um(
            "SELECT cdi, selic FROM macro ORDER BY data DESC LIMIT 1"
        )
        cdi_local = _row_get(row, "cdi")
        selic_local = _row_get(row, "selic")

        if cdi_local is not None:
            fonte = "CDI_LOCAL"
            valor = round((1 + float(cdi_local) / 100) ** (dias / 252) - 1, 4) * 100
            return valor, fonte

        if selic_local is not None:
            fonte = "SELIC_LOCAL"
            valor = round((1 + float(selic_local) / 100) ** (dias / 252) - 1, 4) * 100
            return valor, fonte

    except Exception as erro:
        observabilidade.registrar_erro(
            "aprendizado.avaliador",
            erro,
            fonte="BANCO_LOCAL",
            contexto={"funcao": "_benchmark_periodo", "dias": dias},
        )

    observabilidade.registrar_evento(
        "WARNING",
        "aprendizado.avaliador",
        "Benchmark indisponível; usando fallback defensivo",
        contexto={"dias": dias},
    )

    return 0.0, "FALLBACK_ZERO"


def _dividendos_periodo(ticker: str, data_inicio: str, data_fim: str) -> float:
    try:
        rows = db.buscar_todos(
            """
            SELECT SUM(valor) as total FROM dividendos
            WHERE ticker = ?
            AND data_pagamento >= ?
            AND data_pagamento <= ?
            """,
            (ticker, data_inicio, data_fim),
        )
        total = _row_get(rows[0], "total") if rows else None
        return float(total) if total else 0.0
    except Exception as erro:
        observabilidade.registrar_erro(
            "aprendizado.avaliador",
            erro,
            ticker=ticker,
            contexto={"funcao": "_dividendos_periodo"},
        )
        return 0.0


def _preco_na_data(ticker: str, data_ref: str) -> float | None:
    try:
        row = db.buscar_um(
            """
            SELECT preco FROM indicadores
            WHERE ticker = ? AND data <= ?
            ORDER BY data DESC LIMIT 1
            """,
            (ticker, data_ref),
        )
        preco = _row_get(row, "preco") if row else None
        return float(preco) if preco else None
    except Exception as erro:
        observabilidade.registrar_erro(
            "aprendizado.avaliador",
            erro,
            ticker=ticker,
            contexto={"funcao": "_preco_na_data", "data_ref": data_ref},
        )
        return None


def _resultado_existe(decisao_id: int, janela_dias: int) -> bool:
    row = db.buscar_um(
        """
        SELECT id FROM decisoes_resultado
        WHERE decisao_id = ? AND janela_dias = ?
        LIMIT 1
        """,
        (decisao_id, janela_dias),
    )
    return bool(row)


def _marcar_avaliada_se_completa(decisao_id: int) -> None:
    if _resultado_existe(decisao_id, 90) and _resultado_existe(decisao_id, 365):
        db.executar("UPDATE decisoes SET avaliada = 1 WHERE id = ?", (decisao_id,))
