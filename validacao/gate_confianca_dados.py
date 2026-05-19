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


def _gate_result(
    gate: int,
    status: str,
    motivo: str,
    *,
    eliminado: bool = False,
    metricas: dict[str, Any] | None = None,
    fontes: list[str] | None = None,
    penalidades: list[str] | None = None,
    motivos: list[str] | None = None,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Contrato padrão de saída dos gates.

    Mantém campos legados no mesmo payload para não quebrar consumidores atuais,
    mas garante a estrutura comum exigida pela Fase 3:
    gate, status, aprovado, eliminado, motivos, metricas, fontes e penalidades.
    """
    resultado = {
        "gate": gate,
        "status": status,
        "aprovado": not eliminado and not status.startswith("VETO"),
        "eliminado": eliminado,
        "motivo": motivo,
        "motivos": motivos or [motivo],
        "metricas": metricas or {},
        "fontes": fontes or [],
        "penalidades": penalidades or [],
    }
    if extras:
        resultado.update(extras)
    return resultado


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


def gate55_confianca_dados(ticker: str, contexto: dict | None = None) -> dict[str, Any]:
    """
    Executa Gate 5.5 com foco inicial em dados patrimoniais críticos.

    Se o contexto em memória estiver presente, avalia apenas os dados já
    normalizados no contexto. Nesse caminho não consulta SQLite/rede e não grava
    logs em disco, preservando o Zero DB Query Mode.
    """
    ticker_norm = ticker.upper().replace(".SA", "").strip()

    try:
        if contexto:
            patrimonio = _patrimonio_a_partir_contexto(contexto)
        else:
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

        metricas = {
            "score_confianca_dados": score,
            "nivel_uso_dados": nivel,
            "usou_cvm_patrimonial": usou_cvm,
            "fallback_patrimonial_usado": fallback,
            "fonte_patrimonial": fonte,
        }
        extras = {
            "score_confianca_dados": score,
            "nivel_uso_dados": nivel,
            "usou_cvm_patrimonial": usou_cvm,
            "fallback_patrimonial_usado": fallback,
            "fonte_patrimonial": fonte,
            "patrimonio_resolvido": patrimonio,
        }
        resultado = _gate_result(
            55,
            status,
            motivo,
            eliminado=eliminado,
            metricas=metricas,
            fontes=[fonte],
            penalidades=penalidades,
            extras=extras,
        )

        if not contexto:
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
        if not contexto:
            observabilidade.registrar_erro(
                "validacao.gate55_confianca_dados",
                erro,
                ticker=ticker_norm,
            )
        return _gate_result(
            55,
            "BLOQUEADO_ERRO_CONFIANCA_DADOS",
            f"Erro ao avaliar confiança estrutural dos dados: {erro}",
            eliminado=True,
            metricas={
                "score_confianca_dados": 0.0,
                "nivel_uso_dados": "INSUFICIENTE",
                "usou_cvm_patrimonial": False,
                "fallback_patrimonial_usado": False,
                "fonte_patrimonial": "ERRO",
            },
            fontes=["ERRO"],
            penalidades=["Falha no Gate 5.5."],
            extras={
                "score_confianca_dados": 0.0,
                "nivel_uso_dados": "INSUFICIENTE",
                "usou_cvm_patrimonial": False,
                "fallback_patrimonial_usado": False,
                "fonte_patrimonial": "ERRO",
            },
        )