"""
processamento/analise_dre.py
Leitura fundamentalista CVM para complementar o score/gates do FIIA.

Objetivo:
- usar dados oficiais já coletados do informe trimestral quando disponíveis;
- detectar deterioração de receita, inadimplência e fragilidade operacional;
- não substituir Fundamentus de uma vez: atua como camada complementar CVM-first.
"""
from __future__ import annotations

from statistics import mean
from typing import Any

from banco import db


def _rows_para_dicts(rows) -> list[dict[str, Any]]:
    return [dict(r) for r in rows] if rows else []


def inadimplencia_media(ticker: str) -> float | None:
    """Inadimplência média ponderada por área/receita no último trimestre disponível."""
    ticker = ticker.upper().replace(".SA", "")
    rows = db.buscar_todos(
        """
        SELECT inadimplencia_pct, area, receita_pct
        FROM inf_trimestral_imoveis
        WHERE ticker = ?
          AND data_referencia = (
              SELECT MAX(data_referencia)
              FROM inf_trimestral_imoveis
              WHERE ticker = ?
          )
          AND inadimplencia_pct IS NOT NULL
        """,
        (ticker, ticker),
    )
    dados = _rows_para_dicts(rows)
    if not dados:
        return None

    pesos = []
    valores = []
    for r in dados:
        valor = r.get("inadimplencia_pct")
        if valor is None:
            continue
        peso = r.get("receita_pct") or r.get("area") or 1
        pesos.append(float(peso))
        valores.append(float(valor))

    if not valores:
        return None
    total_pesos = sum(pesos) or len(valores)
    return round(sum(v * p for v, p in zip(valores, pesos)) / total_pesos, 2)


def concentracao_receita_top1(ticker: str) -> float | None:
    """Maior participação de receita por imóvel no último trimestre."""
    ticker = ticker.upper().replace(".SA", "")
    row = db.buscar_um(
        """
        SELECT MAX(receita_pct) AS top1
        FROM inf_trimestral_imoveis
        WHERE ticker = ?
          AND data_referencia = (
              SELECT MAX(data_referencia)
              FROM inf_trimestral_imoveis
              WHERE ticker = ?
          )
        """,
        (ticker, ticker),
    )
    return round(float(row["top1"]), 2) if row and row["top1"] is not None else None


def evolucao_receita_3t(ticker: str) -> float | None:
    """
    Aproxima tendência de receita usando soma de receita_pct por trimestre.

    O informe trimestral disponível no projeto traz percentual de receitas por imóvel,
    não DRE completa. Esta métrica é conservadora: mede deterioração relativa da base
    de receitas reportada, sem fingir precisão contábil inexistente.
    """
    ticker = ticker.upper().replace(".SA", "")
    rows = db.buscar_todos(
        """
        SELECT data_referencia, SUM(receita_pct) AS receita_total
        FROM inf_trimestral_imoveis
        WHERE ticker = ? AND receita_pct IS NOT NULL
        GROUP BY data_referencia
        ORDER BY data_referencia DESC
        LIMIT 3
        """,
        (ticker,),
    )
    dados = list(reversed(_rows_para_dicts(rows)))
    if len(dados) < 2:
        return None

    inicio = dados[0].get("receita_total")
    fim = dados[-1].get("receita_total")
    if not inicio:
        return None
    return round((float(fim) / float(inicio) - 1) * 100, 2)


def qualidade_cvm(ticker: str) -> dict[str, Any]:
    """Retorna score complementar CVM de 0 a 100 e alertas auditáveis."""
    ticker = ticker.upper().replace(".SA", "")
    inad = inadimplencia_media(ticker)
    conc = concentracao_receita_top1(ticker)
    evol = evolucao_receita_3t(ticker)

    score = 100
    alertas: list[str] = []
    penalidades: list[str] = []
    campos_usados = []

    if inad is not None:
        campos_usados.append("inadimplencia_media")
        if inad >= 10:
            score -= 30
            alertas.append(f"Inadimplência CVM elevada ({inad:.2f}%).")
        elif inad >= 5:
            score -= 15
            penalidades.append(f"Inadimplência CVM em atenção ({inad:.2f}%).")

    if conc is not None:
        campos_usados.append("concentracao_receita_top1")
        if conc >= 50:
            score -= 25
            alertas.append(f"Concentração de receita muito alta no maior imóvel ({conc:.2f}%).")
        elif conc >= 30:
            score -= 10
            penalidades.append(f"Concentração relevante no maior imóvel ({conc:.2f}%).")

    if evol is not None:
        campos_usados.append("evolucao_receita_3t")
        if evol <= -15:
            score -= 25
            alertas.append(f"Deterioração relevante da base de receita em 3 trimestres ({evol:.2f}%).")
        elif evol <= -5:
            score -= 10
            penalidades.append(f"Receita em queda nos últimos trimestres ({evol:.2f}%).")

    if not campos_usados:
        return {
            "ticker": ticker,
            "disponivel": False,
            "score_cvm": None,
            "motivo": "Sem dados trimestrais CVM suficientes para análise DRE/complementar.",
            "campos_usados": [],
            "alertas": [],
            "penalidades": [],
        }

    return {
        "ticker": ticker,
        "disponivel": True,
        "score_cvm": max(0, min(100, score)),
        "inadimplencia_media": inad,
        "concentracao_receita_top1": conc,
        "evolucao_receita_3t": evol,
        "campos_usados": campos_usados,
        "alertas": alertas,
        "penalidades": penalidades,
        "fonte": "CVM_INF_TRIMESTRAL",
    }
