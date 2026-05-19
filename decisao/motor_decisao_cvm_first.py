"""
decisao/motor_decisao_cvm_first.py

Adaptador CVM-first para o motor de decisão atual.
"""
from __future__ import annotations

from typing import Any

from decisao import motor_decisao
from decisao.objeto_decisao import normalizar_contrato_decisao
from servicos.resolvedor_patrimonial import resolver_patrimonio
from sistema import observabilidade
from validacao.gate_confianca_dados import gate55_confianca_dados

ACOES_FORTES = {"COMPRAR", "COMPRAR_PARCIAL", "COMPRAR_PARCIALMENTE"}


def _normalizar_acao(acao: str | None) -> str:
    if not acao:
        return "MONITORAR"
    return acao.upper().strip()


def _rebaixar_por_fallback_patrimonial(acao: str, patrimonio: dict[str, Any]) -> str:
    acao_norm = _normalizar_acao(acao)
    if patrimonio.get("usou_cvm"):
        return acao_norm
    if acao_norm == "COMPRAR":
        return "COMPRAR_PARCIAL"
    if acao_norm in {"COMPRAR_PARCIAL", "COMPRAR_PARCIALMENTE"}:
        return "MONITORAR"
    return acao_norm


def _aplicar_gate55_na_decisao(acao: str, gate55: dict[str, Any]) -> str:
    acao_norm = _normalizar_acao(acao)
    status = gate55.get("status", "")

    if status in {"BLOQUEADO_CONFIANCA_DADOS_INSUFICIENTE", "BLOQUEADO_ERRO_CONFIANCA_DADOS"}:
        return "MONITORAR"
    if status == "BLOQUEADO_COMPRA_FORTE_DADOS_FRAGEIS":
        if acao_norm == "COMPRAR":
            return "COMPRAR_PARCIAL"
        if acao_norm in {"COMPRAR_PARCIAL", "COMPRAR_PARCIALMENTE"}:
            return "MONITORAR"
    if status == "PENALIZADO_CONFIANCA_DADOS" and acao_norm == "COMPRAR":
        return "COMPRAR_PARCIAL"
    return acao_norm


def _registrar_gate55(veredito: dict[str, Any], gate55: dict[str, Any]) -> None:
    """Inclui o Gate 5.5 na trilha preservando o contrato padronizado."""
    status = gate55.get("status", "NAO_REGISTRADO")
    trilha = veredito.setdefault("trilha_gates", [])
    marcador = f"G5.5:{status}"
    if marcador not in trilha:
        trilha.append(marcador)

    detalhes = veredito.setdefault("gates_detalhes", {})
    detalhes["55"] = {
        "gate": gate55.get("gate", 55),
        "status": status,
        "aprovado": gate55.get("aprovado", not gate55.get("eliminado", False)),
        "eliminado": gate55.get("eliminado", False),
        "motivo": gate55.get("motivo"),
        "motivos": gate55.get("motivos") or [gate55.get("motivo")],
        "metricas": gate55.get("metricas") or {
            "score_confianca_dados": gate55.get("score_confianca_dados"),
            "nivel_uso_dados": gate55.get("nivel_uso_dados"),
            "fonte_patrimonial": gate55.get("fonte_patrimonial"),
        },
        "fontes": gate55.get("fontes") or [gate55.get("fonte_patrimonial")],
        "penalidades": gate55.get("penalidades") or [],
        # Campos legados preservados para consumidores existentes.
        "score_confianca_dados": gate55.get("score_confianca_dados"),
        "nivel_uso_dados": gate55.get("nivel_uso_dados"),
        "fonte_patrimonial": gate55.get("fonte_patrimonial"),
    }

    if gate55.get("eliminado"):
        veredito["gate_parada"] = 55


def _patrimonio_a_partir_contexto(contexto: dict) -> dict[str, Any]:
    """
    Mapeia os atributos patrimoniais resolvidos do contexto em memória para
    um dicionário compatível com resolver_patrimonio (Achado 2).
    """
    return {
        "patrimonio_liquido": contexto.get("patrimonio_liquido"),
        "valor_patrimonial_cota": contexto.get("vpa"),
        "pvp": contexto.get("pvp"),
        "fonte_patrimonial": contexto.get("patrimonio_fonte") or "FALLBACK_BANCO_ATUAL",
        "usou_cvm": contexto.get("patrimonio_fonte") == "CVM_INF_MENSAL",
        "fallback_usado": contexto.get("patrimonio_fonte") != "CVM_INF_MENSAL",
        "confianca_dados": {
            "score_global": contexto.get("score_confianca", 0.0),
            "nivel_uso": contexto.get("nivel_uso_dados", "INSUFICIENTE"),
            "campos_criticos_frageis": contexto.get("campos_vencidos") or [],
            "divergencias": [],
            "observacoes": [],
            "detalhes": [],
        },
    }


def decidir(
    ticker: str,
    score_ia: float | None = None,
    riscos_ia: list | None = None,
    tom_gestor: str | None = None,
    ia_status: str = "INDISPONIVEL",
    contexto: dict | None = None,
) -> dict:
    ticker_norm = ticker.upper().replace(".SA", "").strip()

    try:
        veredito = motor_decisao.decidir(
            ticker_norm,
            score_ia=score_ia,
            riscos_ia=riscos_ia,
            tom_gestor=tom_gestor,
            ia_status=ia_status,
            contexto=contexto,
        )

        if veredito.get("decisao") == "BLOQUEADO_CONTEXTO_INCOMPLETO":
            return normalizar_contrato_decisao(veredito, contexto)

        if contexto:
            patrimonio = _patrimonio_a_partir_contexto(contexto)
        else:
            patrimonio = resolver_patrimonio(ticker_norm)

        gate55 = gate55_confianca_dados(ticker_norm, contexto=contexto)
        _registrar_gate55(veredito, gate55)

        decisao_original = _normalizar_acao(veredito.get("decisao") or veredito.get("status"))
        decisao_pos_fallback = _rebaixar_por_fallback_patrimonial(decisao_original, patrimonio)
        decisao_final = _aplicar_gate55_na_decisao(decisao_pos_fallback, gate55)

        veredito["gate55_confianca_dados"] = gate55
        veredito["score_confianca_dados"] = gate55.get("score_confianca_dados")
        veredito["nivel_uso_dados"] = gate55.get("nivel_uso_dados")
        veredito["patrimonio_resolvido"] = patrimonio
        veredito["fonte_patrimonial"] = patrimonio.get("fonte_patrimonial")
        veredito["usou_cvm_patrimonial"] = patrimonio.get("usou_cvm", False)
        veredito["fallback_patrimonial_usado"] = patrimonio.get("fallback_usado", False)
        veredito["pvp_cvm"] = patrimonio.get("pvp") if patrimonio.get("usou_cvm") else None
        veredito["valor_patrimonial_cota_cvm"] = patrimonio.get("valor_patrimonial_cota") if patrimonio.get("usou_cvm") else None
        veredito["patrimonio_liquido_cvm"] = patrimonio.get("patrimonio_liquido") if patrimonio.get("usou_cvm") else None

        motivos_extra = []
        if decisao_pos_fallback != decisao_original:
            motivos_extra.append(
                f"Decisão rebaixada por ausência de dado patrimonial CVM: {decisao_original} -> {decisao_pos_fallback}."
            )
        if decisao_final != decisao_pos_fallback:
            motivos_extra.append(
                f"Gate 5.5 ajustou a decisão: {decisao_pos_fallback} -> {decisao_final}. Status: {gate55.get('status')}."
            )
        if decisao_final != decisao_original:
            veredito["decisao_original"] = decisao_original
            veredito["decisao"] = decisao_final
            veredito["motivo"] = f"{veredito.get('motivo', '')} {' '.join(motivos_extra)}".strip()

        if not contexto:
            observabilidade.registrar_evento(
                "INFO",
                "decisao.motor_cvm_first",
                "Decisão processada com CVM-first e Gate 5.5",
                ticker=ticker_norm,
                contexto={
                    "decisao": veredito.get("decisao"),
                    "fonte_patrimonial": veredito.get("fonte_patrimonial"),
                    "gate55_status": gate55.get("status"),
                },
            )

        return normalizar_contrato_decisao(veredito, contexto)

    except Exception as erro:
        if not contexto:
            observabilidade.registrar_erro("decisao.motor_cvm_first", erro, ticker=ticker_norm)
        return normalizar_contrato_decisao({
            "ticker": ticker_norm,
            "decisao": "MONITORAR",
            "status": "ERRO_MOTOR_CVM_FIRST",
            "motivo": f"Falha controlada no motor CVM-first: {erro}",
            "gate_parada": 55,
            "trilha_gates": ["G5.5:BLOQUEADO_ERRO_CONFIANCA_DADOS"],
            "gates_detalhes": {
                "55": {
                    "gate": 55,
                    "status": "BLOQUEADO_ERRO_CONFIANCA_DADOS",
                    "aprovado": False,
                    "eliminado": True,
                    "motivo": str(erro),
                    "motivos": [str(erro)],
                    "metricas": {},
                    "fontes": ["ERRO"],
                    "penalidades": ["Falha no adaptador CVM-first."],
                }
            },
            "usou_cvm_patrimonial": False,
            "fallback_patrimonial_usado": False,
        }, contexto)