"""
servicos/resolvedor_patrimonial.py

Resolvedor patrimonial canônico do FIIA.

Regra central:
1. Tentar CVM primeiro para VP/cota e patrimônio líquido.
2. Usar banco atual/Fundamentus apenas como fallback auxiliar.
3. Expor a fonte usada e o nível de confiança operacional.

Este módulo permite migrar o motor gradualmente sem quebrar a lógica atual.
"""
from __future__ import annotations

from typing import Any

from banco import db
from servicos import cvm_fii_service
from sistema import observabilidade
from validacao.confianca_fonte import avaliar_campo
from validacao.relatorio_confianca import gerar_relatorio_confianca


def _buscar_indicador_atual(ticker: str) -> dict[str, Any]:
    row = db.buscar_um(
        "SELECT * FROM indicadores WHERE ticker = ? ORDER BY data DESC LIMIT 1",
        (ticker.upper().replace(".SA", ""),),
    )
    return dict(row) if row else {}


def resolver_patrimonio(ticker: str) -> dict[str, Any]:
    """
    Resolve dados patrimoniais para o ticker.

    Retorna sempre um dict com:
    - patrimonio_liquido
    - valor_patrimonial_cota
    - pvp
    - fonte_patrimonial
    - usou_cvm
    - fallback_usado
    - confianca_dados
    """
    ticker_norm = ticker.upper().replace(".SA", "").strip()

    try:
        ind = _buscar_indicador_atual(ticker_norm)
        preco = ind.get("preco")

        cvm = cvm_fii_service.calcular_pvp_cvm(ticker_norm, preco)
        campos_confianca = []

        if cvm and cvm.get("valor_patrimonial_cota_cvm"):
            patrimonio = cvm.get("patrimonio_liquido_cvm")
            vp_cota = cvm.get("valor_patrimonial_cota_cvm")
            pvp = cvm.get("pvp_cvm")

            campos_confianca.extend([
                avaliar_campo("patrimonio_liquido", "CVM", patrimonio),
                avaliar_campo("valor_patrimonial_cota", "CVM", vp_cota),
                avaliar_campo("pvp", "CVM", pvp),
            ])

            relatorio = gerar_relatorio_confianca(
                ticker_norm,
                campos_confianca,
                campos_criticos=["patrimonio_liquido", "valor_patrimonial_cota", "pvp"],
            )

            return {
                "ticker": ticker_norm,
                "patrimonio_liquido": patrimonio,
                "valor_patrimonial_cota": vp_cota,
                "pvp": pvp,
                "preco": preco,
                "fonte_patrimonial": "CVM_INF_MENSAL",
                "usou_cvm": True,
                "fallback_usado": False,
                "competencia_cvm": cvm.get("competencia"),
                "cnpj_fundo": cvm.get("cnpj_fundo"),
                "arquivo_origem": cvm.get("arquivo_origem"),
                "confianca_dados": relatorio.to_dict(),
            }

        # Fallback auxiliar: banco atual, usualmente preenchido por Fundamentus
        patrimonio_fb = ind.get("patrimonio_liquido")
        vp_cota_fb = ind.get("vpa")
        pvp_fb = ind.get("pvp")

        campos_confianca.extend([
            avaliar_campo("patrimonio_liquido", "Fundamentus", patrimonio_fb),
            avaliar_campo("valor_patrimonial_cota", "Fundamentus", vp_cota_fb),
            avaliar_campo("pvp", "Fundamentus", pvp_fb),
        ])

        relatorio = gerar_relatorio_confianca(
            ticker_norm,
            campos_confianca,
            campos_criticos=["patrimonio_liquido", "valor_patrimonial_cota", "pvp"],
        )

        observabilidade.registrar_evento(
            "WARNING",
            "servicos.resolvedor_patrimonial",
            "Fallback patrimonial usado por ausência de CVM",
            ticker=ticker_norm,
        )

        return {
            "ticker": ticker_norm,
            "patrimonio_liquido": patrimonio_fb,
            "valor_patrimonial_cota": vp_cota_fb,
            "pvp": pvp_fb,
            "preco": preco,
            "fonte_patrimonial": "FALLBACK_BANCO_ATUAL",
            "usou_cvm": False,
            "fallback_usado": True,
            "competencia_cvm": None,
            "cnpj_fundo": None,
            "arquivo_origem": None,
            "confianca_dados": relatorio.to_dict(),
        }

    except Exception as erro:
        observabilidade.registrar_erro(
            "servicos.resolvedor_patrimonial",
            erro,
            ticker=ticker_norm,
        )
        return {
            "ticker": ticker_norm,
            "patrimonio_liquido": None,
            "valor_patrimonial_cota": None,
            "pvp": None,
            "preco": None,
            "fonte_patrimonial": "ERRO",
            "usou_cvm": False,
            "fallback_usado": False,
            "erro": str(erro),
        }
