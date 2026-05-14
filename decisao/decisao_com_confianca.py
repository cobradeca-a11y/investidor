"""
decisao/decisao_com_confianca.py

Adaptador consolidado de decisão com confiança.

Agora esta camada usa o motor CVM-first como base, preservando:
- prioridade patrimonial CVM;
- fallback auxiliar quando necessário;
- Gate 5.5 de confiança estrutural dos dados;
- RelatorioConfianca para visão consolidada da análise.
"""
from __future__ import annotations

from typing import Any

from banco import db
from decisao import motor_decisao_cvm_first
from sistema import observabilidade
from validacao.confianca_fonte import avaliar_campo
from validacao.relatorio_confianca import gerar_relatorio_confianca, aplicar_confianca_na_acao


CAMPOS_CRITICOS = [
    "preco",
    "pvp",
    "liquidez_diaria",
    "vpa",
    "dy_12m",
    "segmento",
]


def _buscar_base_confianca(ticker: str) -> tuple[dict[str, Any], dict[str, Any]]:
    ind_row = db.buscar_um(
        "SELECT * FROM indicadores WHERE ticker = ? ORDER BY data DESC LIMIT 1",
        (ticker,),
    )
    fii_row = db.buscar_um("SELECT * FROM fiis WHERE ticker = ?", (ticker,))

    return (dict(ind_row) if ind_row else {}, dict(fii_row) if fii_row else {})


def _montar_campos_confianca(ticker: str, veredito: dict[str, Any]) -> list:
    ind, fii = _buscar_base_confianca(ticker)
    patrimonio = veredito.get("patrimonio_resolvido", {}) or {}

    fonte_patrimonial = veredito.get("fonte_patrimonial") or patrimonio.get("fonte_patrimonial") or "Fundamentus"

    campos = [
        avaliar_campo("preco", "Fundamentus", ind.get("preco")),
        avaliar_campo("pvp", fonte_patrimonial, patrimonio.get("pvp") or ind.get("pvp")),
        avaliar_campo("liquidez_diaria", "Fundamentus", ind.get("liquidez_diaria")),
        avaliar_campo("vpa", fonte_patrimonial, patrimonio.get("valor_patrimonial_cota") or ind.get("vpa")),
        avaliar_campo("dy_12m", "Fundamentus", ind.get("dy_12m")),
        avaliar_campo("vacancia_fisica", "Fundamentus", ind.get("vacancia_fisica")),
        avaliar_campo("patrimonio_liquido", fonte_patrimonial, patrimonio.get("patrimonio_liquido") or ind.get("patrimonio_liquido")),
        avaliar_campo("segmento", "base_local", fii.get("segmento")),
    ]

    return campos


def decidir(
    ticker: str,
    score_ia: float | None = None,
    riscos_ia: list | None = None,
    tom_gestor: str | None = None,
    ia_status: str = "INDISPONIVEL",
) -> dict:
    """
    Executa o motor CVM-first e adiciona relatório consolidado de confiança.
    """
    ticker = ticker.upper().replace(".SA", "").strip()

    try:
        veredito = motor_decisao_cvm_first.decidir(
            ticker,
            score_ia=score_ia,
            riscos_ia=riscos_ia,
            tom_gestor=tom_gestor,
            ia_status=ia_status,
        )

        campos = _montar_campos_confianca(ticker, veredito)
        relatorio = gerar_relatorio_confianca(
            ticker,
            campos,
            campos_criticos=CAMPOS_CRITICOS,
        )

        decisao_original = veredito.get("decisao") or veredito.get("status") or "MONITORAR"
        decisao_ajustada = aplicar_confianca_na_acao(decisao_original, relatorio)

        if decisao_ajustada != decisao_original:
            motivo_extra = (
                f" Decisão rebaixada por relatório consolidado de confiança: "
                f"{decisao_original} -> {decisao_ajustada}. "
                f"Nível: {relatorio.nivel_uso.value}."
            )
            veredito["motivo"] = f"{veredito.get('motivo', '')}{motivo_extra}".strip()
            veredito.setdefault("decisao_original", decisao_original)
            veredito["decisao"] = decisao_ajustada

        veredito["confianca_dados"] = relatorio.to_dict()
        veredito["score_confianca_dados_consolidado"] = relatorio.score_global
        veredito["nivel_uso_dados_consolidado"] = relatorio.nivel_uso.value

        observabilidade.registrar_evento(
            "INFO",
            "decisao.com_confianca",
            "Decisão consolidada com motor CVM-first e confiança dos dados",
            ticker=ticker,
            contexto={
                "decisao": veredito.get("decisao"),
                "score_confianca_dados": relatorio.score_global,
                "nivel_uso_dados": relatorio.nivel_uso.value,
                "fonte_patrimonial": veredito.get("fonte_patrimonial"),
                "usou_cvm_patrimonial": veredito.get("usou_cvm_patrimonial"),
            },
        )

        return veredito

    except Exception as erro:
        observabilidade.registrar_erro(
            "decisao.com_confianca",
            erro,
            ticker=ticker,
        )
        return {
            "ticker": ticker,
            "decisao": "MONITORAR",
            "status": "ERRO_DECISAO_COM_CONFIANCA",
            "motivo": f"Falha controlada na decisão com confiança: {erro}",
            "score_confianca_dados": 0.0,
            "nivel_uso_dados": "INSUFICIENTE",
            "usou_cvm_patrimonial": False,
        }
