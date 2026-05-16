"""
backtest/maquina_tempo.py
Backtest auditável do FIIA.

Objetivo:
- eliminar o protótipo antigo baseado apenas em DY >= 8%;
- usar o motor real de decisão (`decisao.motor_decisao.decidir`);
- separar claramente dados disponíveis na data da decisão de dados usados apenas
  para avaliação futura;
- comparar o resultado contra CDI histórico gravado no banco, sem CDI fixo.

Limitação importante:
Este módulo usa o motor real com o estado atual do banco. Para validade
institucional plena, o banco precisa manter snapshots históricos dos indicadores
por data. Sem snapshot, o resultado é marcado como `validade_institucional=False`
para impedir falsa precisão.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from banco import db
from coleta.api_yfinance import pegar_preco_historico
from decisao.motor_decisao import decidir

_DECISOES_ENTRADA = {"COMPRAR", "COMPRAR_PARCIAL"}
_DECISOES_NAO_ENTRADA = {"AGUARDAR", "MONITORAR", "EVITAR", "ELIMINADO"}


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
    """
    Retorna CDI acumulado aproximado no período usando a tabela macro.

    Aceita duas convenções comuns no banco:
    - CDI em percentual anual, ex.: 10.65;
    - CDI em fator diário/percentual diário, quando menor que 1.

    Se não houver dados suficientes, retorna None. Não usa fallback fixo.
    """
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


def executar_backtest(
    ticker: str,
    ano_inicio: int | None = None,
    ano_fim: int | None = None,
    dia_mes_decisao: str = "01-10",
    horizonte_anos: int = 1,
) -> dict[str, Any]:
    """
    Executa backtest anual do ticker.

    Importante: dividendos entre data_decisao e data_avaliacao são usados somente
    como RESULTADO realizado, nunca como entrada da decisão. A decisão vem do
    motor real (`decidir`) e é marcada como não institucional se o banco não tiver
    snapshot histórico dos indicadores na data simulada.
    """
    ticker = ticker.upper().strip()
    hoje = date.today()
    ano_fim = ano_fim or (hoje.year - horizonte_anos)
    ano_inicio = ano_inicio or max(2018, ano_fim - 4)

    resultados: list[dict[str, Any]] = []
    entradas = 0
    acertos = 0
    avaliaveis = 0

    for ano in range(ano_inicio, ano_fim + 1):
        data_decisao = f"{ano}-{dia_mes_decisao}"
        data_avaliacao = f"{ano + horizonte_anos}-{dia_mes_decisao}"

        preco_entrada = pegar_preco_historico(ticker, data_decisao)
        preco_saida = pegar_preco_historico(ticker, data_avaliacao)
        if not preco_entrada or not preco_saida:
            resultados.append({
                "ano": ano,
                "data_decisao": data_decisao,
                "status": "IGNORADO_SEM_PRECO_HISTORICO",
            })
            continue

        decisao_motor = decidir(ticker)
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

        resultados.append({
            "ano": ano,
            "data_decisao": data_decisao,
            "data_avaliacao": data_avaliacao,
            "status": "AVALIADO",
            "decisao": decisao,
            "motivo": decisao_motor.get("motivo"),
            "gate_parada": decisao_motor.get("gate_parada"),
            "trilha_gates": decisao_motor.get("trilha_gates"),
            "preco_entrada": round(float(preco_entrada), 2),
            "preco_saida": round(float(preco_saida), 2),
            "dividendos_resultado": round(dividendos_resultado, 4),
            "rentabilidade_cotas_pct": round(rentabilidade_cotas * 100, 2),
            "rentabilidade_dividendos_pct": round(rentabilidade_dividendos * 100, 2),
            "rentabilidade_total_pct": round(rentabilidade_total * 100, 2),
            "benchmark_cdi_pct": round(benchmark_cdi * 100, 2) if benchmark_cdi is not None else None,
            "avaliacao": avaliacao,
            "validade_institucional": False,
            "limitacao": "Motor real executado com estado atual do banco; requer snapshots históricos por data para validade institucional plena.",
        })

    taxa_acerto = (acertos / avaliaveis * 100) if avaliaveis else None
    return {
        "ticker": ticker,
        "periodo": {"ano_inicio": ano_inicio, "ano_fim": ano_fim, "horizonte_anos": horizonte_anos},
        "motor_usado": "decisao.motor_decisao.decidir",
        "benchmark": "CDI histórico da tabela macro; sem fallback fixo",
        "look_ahead_bias": "controlado: dividendos futuros usados somente para avaliação de resultado, não para decisão",
        "validade_institucional": False,
        "motivo_validade": "Ainda falta snapshot histórico de indicadores por data para reproduzir a visão exata do passado.",
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
