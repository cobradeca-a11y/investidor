"""
decisao/decisao_com_confianca.py

Adaptador consolidado de decisão com confiança.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from banco import db
from decisao import motor_decisao_cvm_first
from processamento.eventos_fnet import (
    analisar_eventos_ticker,
    aplicar_eventos_na_decisao,
    registrar_evidencia_fnet_aprendizado,
)
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


def _montar_campos_confianca(ticker: str, veredito: dict[str, Any], contexto: dict | None = None) -> list:
    if contexto:
        patrimonio = veredito.get("patrimonio_resolvido", {}) or {}
        fonte_patrimonial = veredito.get("fonte_patrimonial") or patrimonio.get("fonte_patrimonial") or "Fundamentus"
        return [
            avaliar_campo("preco", "Fundamentus", contexto.get("preco")),
            avaliar_campo("pvp", fonte_patrimonial, contexto.get("pvp")),
            avaliar_campo("liquidez_diaria", "Fundamentus", contexto.get("liquidez_diaria")),
            avaliar_campo("vpa", fonte_patrimonial, contexto.get("vpa")),
            avaliar_campo("dy_12m", "Fundamentus", contexto.get("dy_12m")),
            avaliar_campo("vacancia_fisica", "Fundamentus", contexto.get("vacancia_fisica")),
            avaliar_campo("patrimonio_liquido", fonte_patrimonial, contexto.get("patrimonio_liquido")),
            avaliar_campo("segmento", "base_local", contexto.get("segmento")),
        ]

    ind, fii = _buscar_base_confianca(ticker)
    patrimonio = veredito.get("patrimonio_resolvido", {}) or {}
    fonte_patrimonial = veredito.get("fonte_patrimonial") or patrimonio.get("fonte_patrimonial") or "Fundamentus"

    return [
        avaliar_campo("preco", "Fundamentus", ind.get("preco")),
        avaliar_campo("pvp", fonte_patrimonial, patrimonio.get("pvp") or ind.get("pvp")),
        avaliar_campo("liquidez_diaria", "Fundamentus", ind.get("liquidez_diaria")),
        avaliar_campo("vpa", fonte_patrimonial, patrimonio.get("valor_patrimonial_cota") or ind.get("vpa")),
        avaliar_campo("dy_12m", "Fundamentus", ind.get("dy_12m")),
        avaliar_campo("vacancia_fisica", "Fundamentus", ind.get("vacancia_fisica")),
        avaliar_campo("patrimonio_liquido", fonte_patrimonial, patrimonio.get("patrimonio_liquido") or ind.get("patrimonio_liquido")),
        avaliar_campo("segmento", "base_local", fii.get("segmento")),
    ]


def decidir(
    ticker: str,
    score_ia: float | None = None,
    riscos_ia: list | None = None,
    tom_gestor: str | None = None,
    ia_status: str = "INDISPONIVEL",
    contexto: dict | None = None,
) -> dict:
    """
    Executa o motor CVM-first e adiciona:
    - relatório consolidado de confiança;
    - eventos documentais FNET;
    - registro explícito de evidência FNET para aprendizado.
    """
    ticker = ticker.upper().replace(".SA", "").strip()

    # Se contexto foi fornecido diretamente, garante persistência (apenas se explicitamente solicitado)
    if contexto and contexto.get("persistir_contexto", False):
        hoje = contexto.get("data") or date.today().isoformat()
        # Mapeia campos do contexto para a tabela indicadores
        dados_indicadores = {
            "ticker": ticker,
            "data": hoje,
            "preco": contexto.get("preco"),
            "preco_timestamp": contexto.get("preco_timestamp"),
            "preco_fonte": contexto.get("preco_fonte"),
            "preco_moeda": contexto.get("preco_moeda"),
            "pvp": contexto.get("pvp"),
            "liquidez_diaria": contexto.get("liquidez_diaria"),
            "ultimo_dividendo": contexto.get("ultimo_dividendo"),
            "dy_12m": contexto.get("dy_12m"),
            "dy_patrimonial": contexto.get("dy_patrimonial"),
            "vacancia_fisica": contexto.get("vacancia_fisica"),
            "patrimonio_liquido": contexto.get("patrimonio_liquido"),
            "vpa": contexto.get("vpa"),
            "qtd_ativos": contexto.get("qtd_ativos"),
            "fonte": contexto.get("patrimonio_fonte"),
            "confiabilidade": contexto.get("score_confianca"),
            "coletado_em": contexto.get("atualizado_em"),
        }
        db.upsert("indicadores", dados_indicadores)

    try:
        veredito = motor_decisao_cvm_first.decidir(
            ticker,
            score_ia=score_ia,
            riscos_ia=riscos_ia,
            tom_gestor=tom_gestor,
            ia_status=ia_status,
            contexto=contexto,
        )

        if veredito.get("decisao") == "BLOQUEADO_CONTEXTO_INCOMPLETO":
            return veredito

        campos = _montar_campos_confianca(ticker, veredito, contexto)
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

        if contexto:
            eventos_fnet = contexto.get("eventos_fnet") or {
                "ticker": ticker,
                "nivel_risco_documental": "BAIXO",
                "documentos_relevantes": [],
                "total_eventos": 0,
                "sinalizacao_fnet": "NEUTRO"
            }
        else:
            eventos_fnet = analisar_eventos_ticker(ticker)

        veredito = aplicar_eventos_na_decisao(veredito, eventos_fnet)

        if not contexto and veredito.get("status") != "ERRO_DECISAO_COM_CONFIANCA":
            registrar_evidencia_fnet_aprendizado(veredito, eventos_fnet)

        veredito["confianca_dados"] = relatorio.to_dict()
        veredito["score_confianca_dados_consolidado"] = relatorio.score_global
        veredito["nivel_uso_dados_consolidado"] = relatorio.nivel_uso.value


        observabilidade.registrar_evento(
            "INFO",
            "decisao.com_confianca",
            "Decisão consolidada com motor CVM-first, confiança e FNET",
            ticker=ticker,
            contexto={
                "decisao": veredito.get("decisao"),
                "score_confianca_dados": relatorio.score_global,
                "nivel_uso_dados": relatorio.nivel_uso.value,
                "fonte_patrimonial": veredito.get("fonte_patrimonial"),
                "usou_cvm_patrimonial": veredito.get("usou_cvm_patrimonial"),
                "risco_documental_fnet": eventos_fnet.get("nivel_risco_documental"),
                "aprendizado_fnet_simulacao_id": veredito.get("aprendizado_fnet_simulacao_id"),
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
            "risco_documental_fnet": "ERRO",
        }
