"""
aprendizado/paper_trading.py

Executa simulações diárias automáticas do FIIA.

Objetivo:
- registrar decisões do motor;
- medir assertividade futura;
- alimentar calibração supervisionada.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from banco import db
from decisao.decisao_com_confianca import decidir
from aprendizado import tentativa_erro
from sistema import observabilidade


ACOES_VALIDAS = {
    "COMPRAR",
    "COMPRAR_PARCIAL",
    "COMPRAR_PARCIALMENTE",
    "MANTER",
    "MONITORAR",
    "AGUARDAR",
    "EVITAR",
    "REDUZIR",
    "VENDER",
}


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _acao_normalizada(veredito: dict[str, Any]) -> str:
    acao = (
        veredito.get("decisao")
        or veredito.get("status")
        or "MONITORAR"
    )
    acao = str(acao).upper().strip()
    return acao if acao in ACOES_VALIDAS else "MONITORAR"


def executar_paper_trading_diario(limite: int | None = None) -> dict[str, Any]:
    tentativa_erro.garantir_tabelas()

    sql = "SELECT ticker, segmento FROM fiis WHERE COALESCE(ativo, 1) = 1 ORDER BY ticker"
    if limite:
        sql += f" LIMIT {int(limite)}"

    ativos = db.buscar_todos(sql)

    simulacoes = []
    erros = []

    for ativo in ativos:
        ticker = ativo["ticker"]
        segmento = ativo["segmento"]

        try:
            veredito = decidir(ticker)
            acao = _acao_normalizada(veredito)

            simulacao = tentativa_erro.registrar_simulacao(
                ticker=ticker,
                acao_simulada=acao,
                decisao_origem=veredito.get("decisao_original") or acao,
                segmento=segmento,
                score_final=veredito.get("score_final"),
                confianca=veredito.get("nivel_uso_dados_consolidado"),
                risco=veredito.get("risco_documental_fnet"),
                fonte_patrimonial=veredito.get("fonte_patrimonial"),
                gate55_status=veredito.get("gate55_status"),
                payload_json=json.dumps(veredito, ensure_ascii=False, default=str),
            )
            simulacoes.append(simulacao)

        except Exception as erro:
            erros.append({"ticker": ticker, "erro": str(erro)})
            observabilidade.registrar_erro(
                "aprendizado.paper_trading",
                erro,
                ticker=ticker,
            )

    resumo = {
        "executado_em": _agora_iso(),
        "ativos_processados": len(ativos),
        "simulacoes_registradas": len(simulacoes),
        "erros": len(erros),
    }

    observabilidade.registrar_evento(
        "INFO",
        "aprendizado.paper_trading",
        "Paper trading diário executado",
        contexto=resumo,
    )

    return {
        "resumo": resumo,
        "simulacoes": simulacoes,
        "erros_detalhados": erros,
    }
