"""
mercado/cenario_macro.py

Camada de leitura macroeconômica do FIIA.

Objetivo:
- consolidar SELIC, CDI e IPCA;
- classificar regime de juros/inflação;
- traduzir cenário macro em impacto operacional para FIIs;
- alimentar relatórios, auditoria e decisão de carteira.
"""
from __future__ import annotations

from typing import Any

from coleta.api_bcb import obter_selic_atual, obter_cdi_atual, obter_ipca_atual, coletar_macro
from sistema import observabilidade


def _classificar_juros(selic: float | None) -> str:
    if selic is None:
        return "DESCONHECIDO"
    if selic >= 12:
        return "JUROS_ALTOS"
    if selic >= 9:
        return "JUROS_MODERADOS_ALTOS"
    if selic >= 6:
        return "JUROS_MODERADOS"
    return "JUROS_BAIXOS"


def _classificar_inflacao(ipca: float | None) -> str:
    if ipca is None:
        return "DESCONHECIDA"
    if ipca >= 7:
        return "INFLACAO_ALTA"
    if ipca >= 4.5:
        return "INFLACAO_PRESSIONADA"
    if ipca >= 2.5:
        return "INFLACAO_CONTROLADA"
    return "INFLACAO_BAIXA"


def _interpretar_impacto_fii(regime_juros: str, regime_inflacao: str) -> dict[str, Any]:
    alertas: list[str] = []
    favorecidos: list[str] = []
    pressionados: list[str] = []

    if regime_juros in {"JUROS_ALTOS", "JUROS_MODERADOS_ALTOS"}:
        alertas.append("Juros elevados aumentam exigência de margem de segurança e pressionam FIIs de tijolo.")
        favorecidos.append("papel/recebíveis com indexação forte e boa qualidade de crédito")
        pressionados.append("tijolo com baixa revisão contratual e vacância elevada")
    elif regime_juros == "JUROS_BAIXOS":
        favorecidos.append("tijolo de qualidade com crescimento real de renda")
        alertas.append("Juros baixos podem elevar preços e reduzir margem de segurança.")

    if regime_inflacao in {"INFLACAO_ALTA", "INFLACAO_PRESSIONADA"}:
        favorecidos.append("contratos indexados à inflação com repasse saudável")
        pressionados.append("ativos com custos crescentes e baixa capacidade de repasse")
        alertas.append("Inflação pressionada exige atenção à sustentabilidade dos rendimentos.")

    if not alertas:
        alertas.append("Cenário macro sem alerta crítico classificado pela regra atual.")

    return {
        "alertas": alertas,
        "segmentos_favorecidos": favorecidos,
        "segmentos_pressionados": pressionados,
    }


def obter_cenario_macro(forcar_coleta: bool = False) -> dict[str, Any]:
    """Retorna cenário macro estruturado para uso em relatórios e decisões."""
    try:
        if forcar_coleta:
            coletar_macro()

        selic = obter_selic_atual()
        cdi = obter_cdi_atual()
        ipca = obter_ipca_atual()

        regime_juros = _classificar_juros(selic)
        regime_inflacao = _classificar_inflacao(ipca)
        impacto = _interpretar_impacto_fii(regime_juros, regime_inflacao)

        resultado = {
            "selic": selic,
            "cdi": cdi,
            "ipca": ipca,
            "regime_juros": regime_juros,
            "regime_inflacao": regime_inflacao,
            "impacto_fiis": impacto,
        }

        observabilidade.registrar_evento(
            "INFO",
            "mercado.cenario_macro",
            "Cenário macro consolidado",
            contexto=resultado,
        )
        return resultado

    except Exception as erro:
        observabilidade.registrar_erro("mercado.cenario_macro", erro)
        return {
            "selic": None,
            "cdi": None,
            "ipca": None,
            "regime_juros": "ERRO",
            "regime_inflacao": "ERRO",
            "impacto_fiis": {"alertas": [str(erro)], "segmentos_favorecidos": [], "segmentos_pressionados": []},
        }
