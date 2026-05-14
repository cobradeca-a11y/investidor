"""
aprendizado/avaliador.py
Avalia decisões passadas em duas janelas de tempo.

Janela 90 dias  -> avalia TIMING
Janela 365 dias -> avalia TESE

Evolução profissional:
- registra observabilidade;
- evita quebrar por ausência de dados;
- marca decisão como avaliada somente quando 90d e 365d estiverem fechadas;
- mantém compatibilidade com tabela legada de decisões.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from banco import db
from coleta.api_bcb import obter_selic_atual
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


def _cdi_periodo(dias: int) -> float:
    """CDI estimado para o período em %."""
    try:
        selic_anual = obter_selic_atual() or 10.75
        return round((1 + selic_anual / 100) ** (dias / 252) - 1, 4) * 100
    except Exception as erro:
        observabilidade.registrar_erro(
            "aprendizado.avaliador",
            erro,
            fonte="BCB",
            contexto={"funcao": "_cdi_periodo", "dias": dias},
        )
        return round((1 + 10.75 / 100) ** (dias / 252) - 1, 4) * 100


def _dividendos_periodo(ticker: str, data_inicio: str, data_fim: str) -> float:
    """Soma dividendos pagos no período."""
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
    """Preço mais próximo anterior ou igual à data solicitada."""
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


def avaliar_decisao(decisao_id: int, janela_dias: int) -> dict | None:
    """
    Avalia uma decisão específica na janela informada.
    Retorna None quando a janela ainda não fechou ou faltam dados.
    """
    _garantir_tabela()

    decisao = db.buscar_um("SELECT * FROM decisoes WHERE id = ?", (decisao_id,))
    if not decisao:
        return None

    try:
        data_decisao = date.fromisoformat(decisao["data_decisao"])
    except Exception as erro:
        observabilidade.registrar_erro(
            "aprendizado.avaliador",
            erro,
            contexto={"decisao_id": decisao_id, "campo": "data_decisao"},
        )
        return None

    data_avaliacao = data_decisao + timedelta(days=janela_dias)
    if date.today() < data_avaliacao:
        return None

    ticker = decisao["ticker"]
    preco_entrada = _row_get(decisao, "preco_na_decisao") or _row_get(decisao, "preco_atual")
    preco_aval = _preco_na_data(ticker, data_avaliacao.isoformat())

    if not preco_entrada or not preco_aval:
        observabilidade.registrar_evento(
            "WARNING",
            "aprendizado.avaliador",
            "Avaliação ignorada por falta de preço",
            ticker=ticker,
            contexto={"decisao_id": decisao_id, "janela_dias": janela_dias},
        )
        return None

    dividendos = _dividendos_periodo(ticker, decisao["data_decisao"], data_avaliacao.isoformat())
    retorno_preco = (float(preco_aval) / float(preco_entrada) - 1) * 100
    retorno_div = (dividendos / float(preco_entrada)) * 100
    retorno_total = retorno_preco + retorno_div
    cdi_periodo = _cdi_periodo(janela_dias)

    acao = (_row_get(decisao, "decisao") or "").upper()
    decisao_positiva = acao in {"COMPRAR", "COMPRAR_PARCIALMENTE", "MANTER"}
    decisao_defensiva = acao in {"EVITAR", "EVITAR_ENTRADA", "REDUZIR", "VENDER", "AGUARDAR", "MONITORAR"}

    if decisao_positiva:
        acerto = 1 if retorno_total > cdi_periodo else 0
    elif decisao_defensiva:
        acerto = 1 if retorno_total <= cdi_periodo else 0
    else:
        acerto = 1 if retorno_total > cdi_periodo else 0

    tipo = "TIMING" if janela_dias == 90 else "TESE"
    obs = (
        "Avaliação de timing: comportamento relativo no curto prazo."
        if janela_dias == 90
        else "Avaliação de tese: comportamento após janela longa."
    )

    db.executar(
        """
        INSERT OR REPLACE INTO decisoes_resultado
            (decisao_id, ticker, janela_dias, data_avaliacao, preco_entrada,
             preco_avaliacao, retorno_preco, retorno_dividendos, retorno_total,
             retorno_cdi_periodo, acerto, tipo_resultado, observacao)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            decisao_id,
            ticker,
            janela_dias,
            data_avaliacao.isoformat(),
            float(preco_entrada),
            float(preco_aval),
            round(retorno_preco, 2),
            round(retorno_div, 2),
            round(retorno_total, 2),
            round(cdi_periodo, 2),
            acerto,
            tipo,
            obs,
        ),
    )

    _marcar_avaliada_se_completa(decisao_id)

    resultado = {
        "decisao_id": decisao_id,
        "ticker": ticker,
        "janela_dias": janela_dias,
        "retorno_total": round(retorno_total, 2),
        "cdi_periodo": round(cdi_periodo, 2),
        "acerto": bool(acerto),
        "tipo": tipo,
    }

    observabilidade.registrar_evento(
        "INFO",
        "aprendizado.avaliador",
        "Decisão avaliada",
        ticker=ticker,
        contexto=resultado,
    )

    return resultado


def rodar_avaliacoes_pendentes() -> dict:
    """Varre decisões não avaliadas e processa janelas 90/365 dias."""
    _garantir_tabela()

    decisoes = db.buscar_todos("SELECT id, ticker, data_decisao FROM decisoes WHERE avaliada = 0")

    total_90 = 0
    total_365 = 0

    for decisao in decisoes:
        for janela in [90, 365]:
            resultado = avaliar_decisao(decisao["id"], janela)
            if resultado:
                if janela == 90:
                    total_90 += 1
                else:
                    total_365 += 1

    resumo = {"avaliadas_90d": total_90, "avaliadas_365d": total_365}
    observabilidade.registrar_evento(
        "INFO",
        "aprendizado.avaliador",
        "Avaliações pendentes processadas",
        contexto=resumo,
    )
    print(f"[avaliador] {total_90} avaliações de 90d e {total_365} de 365d processadas.")
    return resumo


def taxa_acerto(janela_dias: int = 90) -> dict:
    """Retorna taxa de acerto geral e por segmento."""
    _garantir_tabela()

    rows = db.buscar_todos(
        """
        SELECT r.acerto, f.segmento
        FROM decisoes_resultado r
        JOIN decisoes d ON r.decisao_id = d.id
        LEFT JOIN fiis f ON d.ticker = f.ticker
        WHERE r.janela_dias = ?
        """,
        (janela_dias,),
    )

    if not rows:
        return {"janela_dias": janela_dias, "total": 0, "acerto_pct": 0, "por_segmento": {}}

    total = len(rows)
    acertos = sum(1 for row in rows if row["acerto"])
    pct = round(acertos / total * 100, 1)

    por_seg = {}
    for row in rows:
        seg = _row_get(row, "segmento") or "INDEFINIDO"
        if seg not in por_seg:
            por_seg[seg] = {"total": 0, "acertos": 0}
        por_seg[seg]["total"] += 1
        por_seg[seg]["acertos"] += row["acerto"] or 0

    for seg, dados in por_seg.items():
        total_seg = dados["total"]
        acertos_seg = dados["acertos"]
        dados["pct"] = round(acertos_seg / total_seg * 100, 1) if total_seg else 0

    return {
        "janela_dias": janela_dias,
        "total": total,
        "acerto_pct": pct,
        "por_segmento": por_seg,
    }
