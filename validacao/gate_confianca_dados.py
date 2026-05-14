"""
validacao/gate_confianca_dados.py

Gate 5.5 — Confiança estrutural dos dados.

Objetivo:
- levar confiança para dentro da esteira de Gates;
- bloquear decisão forte quando campos críticos dependem de fallback frágil;
- registrar motivo auditável cedo no pipeline;
- transformar dados frágeis em decisão honesta: MONITORAR / DADOS_INSUFICIENTES.
"""
from __future__ import annotations

from typing import Any

from servicos.resolvedor_patrimonial import resolver_patrimonio
from validacao.relatorio_confianca import NivelUsoDecisao
from sistema import observabilidade


def gate55_confianca_dados(ticker: str) -> dict[str, Any]:
    """
    Executa Gate 5.5 com foco inicial em dados patrimoniais críticos.

    Retorna dict compatível com o padrão de gate do motor_decisao.
    """
    ticker_norm = ticker.upper().replace(".SA", "").strip()

    try:
        patrimonio = resolver_patrimonio(ticker_norm)
        relatorio = patrimonio.get("confianca_dados", {}) or {}
        nivel = relatorio.get("nivel_uso", "INSUFICIENTE")
        score = relatorio.get("score_global", 0.0)
        usou_cvm = patrimonio.get("usou_cvm", False)
        fallback = patrimonio.get("fallback_usado", False)
        fonte = patrimonio.get("fonte_patrimonial", "DESCONHECIDA")

        penalidades = []

        if fallback:
            penalidades.append(
                "Dados patrimoniais vieram de fallback auxiliar; CVM não disponível para o ticker."
            )

        if nivel == NivelUsoDecisao.INSUFICIENTE.value:
            status = "BLOQUEADO_CONFIANCA_DADOS_INSUFICIENTE"
            eliminado = True
            motivo = (
                "Confiança dos dados insuficiente para decisão operacional. "
                f"Fonte patrimonial: {fonte}. Score: {score}."
            )
        elif nivel == NivelUsoDecisao.BLOQUEAR_DECISAO_FORTE.value:
            status = "BLOQUEADO_COMPRA_FORTE_DADOS_FRAGEIS"
            eliminado = False
            motivo = (
                "Dados permitem apenas decisão conservadora; compra forte deve ser bloqueada. "
                f"Fonte patrimonial: {fonte}. Score: {score}."
            )
        elif nivel == NivelUsoDecisao.USAR_COM_CAUTELA.value:
            status = "PENALIZADO_CONFIANCA_DADOS"
            eliminado = False
            motivo = (
                "Dados utilizáveis com cautela; decisão deve reduzir agressividade se necessário. "
                f"Fonte patrimonial: {fonte}. Score: {score}."
            )
        else:
            status = "APROVADO_CONFIANCA_DADOS"
            eliminado = False
            motivo = (
                "Dados críticos possuem confiança operacional suficiente. "
                f"Fonte patrimonial: {fonte}. Score: {score}."
            )

        resultado = {
            "gate": 55,
            "status": status,
            "motivo": motivo,
            "penalidades": penalidades,
            "eliminado": eliminado,
            "score_confianca_dados": score,
            "nivel_uso_dados": nivel,
            "usou_cvm_patrimonial": usou_cvm,
            "fallback_patrimonial_usado": fallback,
            "fonte_patrimonial": fonte,
            "patrimonio_resolvido": patrimonio,
        }

        observabilidade.registrar_evento(
            "INFO",
            "validacao.gate55_confianca_dados",
            "Gate 5.5 executado",
            ticker=ticker_norm,
            contexto={
                "status": status,
                "score_confianca_dados": score,
                "nivel_uso_dados": nivel,
                "fonte_patrimonial": fonte,
            },
        )

        return resultado

    except Exception as erro:
        observabilidade.registrar_erro(
            "validacao.gate55_confianca_dados",
            erro,
            ticker=ticker_norm,
        )
        return {
            "gate": 55,
            "status": "BLOQUEADO_ERRO_CONFIANCA_DADOS",
            "motivo": f"Erro ao avaliar confiança estrutural dos dados: {erro}",
            "penalidades": ["Falha no Gate 5.5."],
            "eliminado": True,
            "score_confianca_dados": 0.0,
            "nivel_uso_dados": "INSUFICIENTE",
            "usou_cvm_patrimonial": False,
            "fallback_patrimonial_usado": False,
            "fonte_patrimonial": "ERRO",
        }
