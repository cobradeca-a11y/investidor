"""
backtest/maquina_tempo.py
Backtest auditável do FIIA com snapshots históricos.

Objetivo:
- usar snapshot histórico real como entrada da decisão;
- impedir uso de preço atual como se fosse histórico;
- separar dados disponíveis na data da decisão de dados usados só para avaliação;
- marcar validade institucional explicitamente em cada resultado.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from banco import db
from coleta.api_yfinance import pegar_preco_historico
from decisao.motor_decisao import decidir
from aprendizado.snapshots import buscar_snapshot_historico, contexto_decisao_de_snapshot

_DECISOES_ENTRADA = {"COMPRAR", "COMPRAR_PARCIAL", "COMPRAR_PARCIALMENTE"}
_DECISOES_NAO_ENTRADA = {"AGUARDAR", "MONITORAR", "EVITAR", "ELIMINADO", "EVITAR_ENTRADA"}


def _iso(d: str | date) -> str:
    if isinstance(d, date):
        return d.isoformat()
    return str(d)[:10]


def _somar_dividendos(ticker: str, inicio: str, fim: str) -> float:
    row = db.buscar_um(
        """
        SELECT SUM(valor) AS total
        FROM dividendos
        WHERE ticker = ?
          AND data_pagamento >= ?
          AND data_pagamento < ?
        """,
        (ticker.upper(), inicio, fim),
    )
    return float(row["total"] or 0.0) if row else 0.0


def _cdi_periodo(inicio: str, fim: str) -> float | None:
    rows = db.buscar_todos(
        """
        SELECT data, cdi
        FROM macro
        WHERE data >= ? AND data < ? AND cdi IS NOT NULL
        ORDER BY data ASC
        """,
        (inicio, fim),
    )
    if not rows:
        return None

    fator = 1.0
    for r in rows:
        cdi = float(r["cdi"])
        if cdi <= 0:
            continue
        if cdi > 1:
            taxa_diaria = (1 + cdi / 100) ** (1 / 252) - 1
        else:
            taxa_diaria = cdi / 100
        fator *= 1 + taxa_diaria
    return fator - 1


def _avaliar_decisao(decisao: str, rentabilidade_total: float, benchmark: float | None) -> dict[str, Any]:
    if benchmark is None:
        return {
            "acerto": None,
            "criterio": "SEM_BENCHMARK_CDI",
            "motivo": "Não há CDI histórico suficiente no banco para avaliar a decisão.",
        }

    superou_cdi = rentabilidade_total > benchmark
    if decisao in _DECISOES_ENTRADA:
        acerto = superou_cdi
        criterio = "ENTRADA_SUPERA_CDI" if acerto else "ENTRADA_PERDE_PARA_CDI"
    elif decisao in _DECISOES_NAO_ENTRADA:
        acerto = not superou_cdi
        criterio = "NAO_ENTRADA_EVITOU_ATIVO_FRACO" if acerto else "NAO_ENTRADA_PERDEU_OPORTUNIDADE"
    else:
        acerto = None
        criterio = "DECISAO_NAO_CLASSIFICADA"

    return {"acerto": acerto, "criterio": criterio, "superou_cdi": superou_cdi}


def _resultado_invalido(
    ano: int,
    data_decisao: str,
    data_avaliacao: str,
    snapshot: dict[str, Any],
    motivo: str,
) -> dict[str, Any]:
    return {
        "ano": ano,
        "data_referencia": data_decisao,
        "data_decisao": data_decisao,
        "data_avaliacao": data_avaliacao,
        "status": "INVALIDO_SEM_SNAPSHOT_INSTITUCIONAL",
        "snapshot_usado": snapshot.get("snapshot_usado") if snapshot else None,
        "hash_snapshot": snapshot.get("hash_snapshot") if snapshot else None,
        "validade_institucional": False,
        "motivo_validade": motivo,
    }


def executar_backtest(
    ticker: str,
    ano_inicio: int | None = None,
    ano_fim: int | None = None,
    dia_mes_decisao: str = "01-10",
    horizonte_anos: int = 1,
    max_defasagem_snapshot_dias: int = 45,
) -> dict[str, Any]:
    """
    Executa backtest anual do ticker usando snapshots históricos reais.

    A decisão recebe contexto derivado do snapshot. Se o snapshot não existir,
    estiver defasado ou não tiver campos mínimos, o resultado é inválido para
    fins institucionais e o motor não é chamado para aquele ponto.
    """
    ticker = ticker.upper().strip()
    hoje = date.today()
    ano_fim = ano_fim or (hoje.year - horizonte_anos)
    ano_inicio = ano_inicio or max(2018, ano_fim - 4)

    resultados: list[dict[str, Any]] = []
    entradas = 0
    acertos = 0
    avaliaveis = 0
    resultados_validos = 0

    for ano in range(ano_inicio, ano_fim + 1):
        data_decisao = f"{ano}-{dia_mes_decisao}"
        data_avaliacao = f"{ano + horizonte_anos}-{dia_mes_decisao}"

        snapshot = buscar_snapshot_historico(
            ticker,
            data_decisao,
            max_defasagem_dias=max_defasagem_snapshot_dias,
        )
        if not snapshot.get("validade_institucional"):
            resultados.append(_resultado_invalido(
                ano,
                data_decisao,
                data_avaliacao,
                snapshot,
                snapshot.get("motivo_validade", "Snapshot histórico insuficiente."),
            ))
            continue

        contexto_snapshot = contexto_decisao_de_snapshot(snapshot)
        if not contexto_snapshot:
            resultados.append(_resultado_invalido(
                ano,
                data_decisao,
                data_avaliacao,
                snapshot,
                "Snapshot histórico não contém campos mínimos para decisão institucional.",
            ))
            continue

        preco_entrada = contexto_snapshot.get("preco")
        preco_saida = pegar_preco_historico(ticker, data_avaliacao)
        if not preco_entrada or not preco_saida:
            resultados.append({
                "ano": ano,
                "data_referencia": data_decisao,
                "data_decisao": data_decisao,
                "data_avaliacao": data_avaliacao,
                "status": "IGNORADO_SEM_PRECO_HISTORICO_AVALIACAO",
                "snapshot_usado": snapshot.get("snapshot_usado"),
                "hash_snapshot": snapshot.get("hash_snapshot"),
                "validade_institucional": False,
                "motivo_validade": "Snapshot da decisão existe, mas falta preço histórico de avaliação futura.",
            })
            continue

        decisao_motor = decidir(ticker, contexto=contexto_snapshot)
        decisao = decisao_motor.get("decisao") or decisao_motor.get("status") or "INDEFINIDA"

        dividendos_resultado = _somar_dividendos(ticker, data_decisao, data_avaliacao)
        rentabilidade_cotas = (float(preco_saida) / float(preco_entrada)) - 1
        rentabilidade_dividendos = dividendos_resultado / float(preco_entrada)
        rentabilidade_total = rentabilidade_cotas + rentabilidade_dividendos
        benchmark_cdi = _cdi_periodo(data_decisao, data_avaliacao)
        avaliacao = _avaliar_decisao(decisao, rentabilidade_total, benchmark_cdi)

        if decisao in _DECISOES_ENTRADA:
            entradas += 1
        if avaliacao["acerto"] is not None:
            avaliaveis += 1
            if avaliacao["acerto"]:
                acertos += 1

        resultados_validos += 1
        resultados.append({
            "ano": ano,
            "data_referencia": data_decisao,
            "data_decisao": data_decisao,
            "data_avaliacao": data_avaliacao,
            "status": "AVALIADO",
            "decisao": decisao,
            "motivo": decisao_motor.get("motivo"),
            "gate_parada": decisao_motor.get("gate_parada"),
            "trilha_gates": decisao_motor.get("trilha_gates"),
            "snapshot_usado": snapshot.get("snapshot_usado"),
            "hash_snapshot": snapshot.get("hash_snapshot"),
            "defasagem_snapshot_dias": snapshot.get("defasagem_dias"),
            "preco_entrada": round(float(preco_entrada), 2),
            "preco_saida": round(float(preco_saida), 2),
            "dividendos_resultado": round(dividendos_resultado, 4),
            "rentabilidade_cotas_pct": round(rentabilidade_cotas * 100, 2),
            "rentabilidade_dividendos_pct": round(rentabilidade_dividendos * 100, 2),
            "rentabilidade_total_pct": round(rentabilidade_total * 100, 2),
            "benchmark_cdi_pct": round(benchmark_cdi * 100, 2) if benchmark_cdi is not None else None,
            "avaliacao": avaliacao,
            "validade_institucional": True,
            "motivo_validade": snapshot.get("motivo_validade"),
        })

    taxa_acerto = (acertos / avaliaveis * 100) if avaliaveis else None
    validade_global = bool(resultados and resultados_validos == len(resultados))
    return {
        "ticker": ticker,
        "periodo": {"ano_inicio": ano_inicio, "ano_fim": ano_fim, "horizonte_anos": horizonte_anos},
        "motor_usado": "decisao.motor_decisao.decidir(contexto=snapshot_historico)",
        "benchmark": "CDI histórico da tabela macro; sem fallback fixo",
        "look_ahead_bias": "controlado: decisão usa snapshot histórico; dividendos e preço futuro são usados apenas na avaliação",
        "validade_institucional": validade_global,
        "motivo_validade": "Todos os pontos usaram snapshot histórico suficiente." if validade_global else "Há pontos sem snapshot histórico suficiente; ver resultados individuais.",
        "entradas_sugeridas": entradas,
        "avaliaveis": avaliaveis,
        "acertos": acertos,
        "taxa_acerto_pct": round(taxa_acerto, 2) if taxa_acerto is not None else None,
        "resultados": resultados,
    }


if __name__ == "__main__":
    import json
    import sys

    ativo = sys.argv[1] if len(sys.argv) > 1 else "KNRI11"
    print(json.dumps(executar_backtest(ativo), ensure_ascii=False, indent=2))
