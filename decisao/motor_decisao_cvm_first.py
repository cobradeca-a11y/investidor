"""
decisao/motor_decisao_cvm_first.py

Adaptador CVM-first para o motor de decisão atual.

Regra:
- mantém o motor_decisao existente funcionando;
- resolve dados patrimoniais via CVM primeiro;
- anexa VP/cota, patrimônio e P/VP oficiais ao veredito;
- expõe fallback quando a CVM não estiver disponível;
- rebaixa decisões fortes se o fundamento patrimonial vier apenas de fallback frágil.

Este arquivo é ponte segura para migrar depois a lógica nativa do motor.
"""
from __future__ import annotations

from typing import Any

from decisao import motor_decisao
from servicos.resolvedor_patrimonial import resolver_patrimonio
from sistema import observabilidade

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


def decidir(
    ticker: str,
    score_ia: float | None = None,
    riscos_ia: list | None = None,
    tom_gestor: str | None = None,
    ia_status: str = "INDISPONIVEL",
) -> dict:
    """Executa decisão com prioridade patrimonial CVM."""
    ticker_norm = ticker.upper().replace(".SA", "").strip()

    try:
        veredito = motor_decisao.decidir(
            ticker_norm,
            score_ia=score_ia,
            riscos_ia=riscos_ia,
            tom_gestor=tom_gestor,
            ia_status=ia_status,
        )

        patrimonio = resolver_patrimonio(ticker_norm)
        decisao_original = _normalizar_acao(veredito.get("decisao") or veredito.get("status"))
        decisao_final = _rebaixar_por_fallback_patrimonial(decisao_original, patrimonio)

        veredito["patrimonio_resolvido"] = patrimonio
        veredito["fonte_patrimonial"] = patrimonio.get("fonte_patrimonial")
        veredito["usou_cvm_patrimonial"] = patrimonio.get("usou_cvm", False)
        veredito["fallback_patrimonial_usado"] = patrimonio.get("fallback_usado", False)
        veredito["pvp_cvm"] = patrimonio.get("pvp") if patrimonio.get("usou_cvm") else None
        veredito["valor_patrimonial_cota_cvm"] = patrimonio.get("valor_patrimonial_cota") if patrimonio.get("usou_cvm") else None
        veredito["patrimonio_liquido_cvm"] = patrimonio.get("patrimonio_liquido") if patrimonio.get("usou_cvm") else None

        if decisao_final != decisao_original:
            veredito["decisao_original"] = decisao_original
            veredito["decisao"] = decisao_final
            motivo_extra = (
                f" Decisão rebaixada por ausência de dado patrimonial CVM: "
                f"{decisao_original} -> {decisao_final}. "
                "Fundamentus/banco atual usado apenas como fallback auxiliar."
            )
            veredito["motivo"] = f"{veredito.get('motivo', '')}{motivo_extra}".strip()

        observabilidade.registrar_evento(
            "INFO",
            "decisao.motor_cvm_first",
            "Decisão processada com resolvedor patrimonial CVM-first",
            ticker=ticker_norm,
            contexto={
                "decisao": veredito.get("decisao"),
                "decisao_original": veredito.get("decisao_original"),
                "usou_cvm_patrimonial": veredito.get("usou_cvm_patrimonial"),
                "fonte_patrimonial": veredito.get("fonte_patrimonial"),
            },
        )

        return veredito

    except Exception as erro:
        observabilidade.registrar_erro(
            "decisao.motor_cvm_first",
            erro,
            ticker=ticker_norm,
        )
        return {
            "ticker": ticker_norm,
            "decisao": "MONITORAR",
            "status": "ERRO_MOTOR_CVM_FIRST",
            "motivo": f"Falha controlada no motor CVM-first: {erro}",
            "usou_cvm_patrimonial": False,
            "fallback_patrimonial_usado": False,
        }
