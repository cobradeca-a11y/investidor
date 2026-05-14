"""
servicos/cvm_fii_service.py

Serviço de acesso canônico aos dados CVM por ticker.

Une:
- tabela mestre ticker -> CNPJ;
- informe mensal CVM por CNPJ;
- cálculo interno de P/VP quando preço de mercado estiver disponível.
"""
from __future__ import annotations

from typing import Any

from banco import db
from coleta import tabela_mestre_fiis, cvm_informe_mensal
from sistema import observabilidade


def dados_patrimoniais_por_ticker(ticker: str) -> dict[str, Any] | None:
    """Retorna último dado patrimonial oficial CVM para um ticker."""
    ticker_norm = ticker.upper().replace(".SA", "").strip()

    try:
        identidade = tabela_mestre_fiis.obter_por_ticker(ticker_norm)
        if not identidade or not identidade.get("cnpj_fundo"):
            observabilidade.registrar_evento(
                "WARNING",
                "servicos.cvm_fii_service",
                "Ticker sem CNPJ na tabela mestre",
                ticker=ticker_norm,
            )
            return None

        cnpj = identidade["cnpj_fundo"]
        informe = cvm_informe_mensal.ultimo_por_cnpj(cnpj)
        if not informe:
            observabilidade.registrar_evento(
                "WARNING",
                "servicos.cvm_fii_service",
                "CNPJ sem informe mensal CVM importado",
                ticker=ticker_norm,
                contexto={"cnpj_fundo": cnpj},
            )
            return None

        return {
            "ticker": ticker_norm,
            "cnpj_fundo": cnpj,
            "cnpj_classe": identidade.get("cnpj_classe"),
            "razao_social": identidade.get("razao_social"),
            "nome_fundo": identidade.get("nome_fundo"),
            "competencia": informe.get("competencia"),
            "patrimonio_liquido_cvm": informe.get("patrimonio_liquido"),
            "valor_patrimonial_cota_cvm": informe.get("valor_patrimonial_cota"),
            "num_cotistas_cvm": informe.get("num_cotistas"),
            "num_cotas_cvm": informe.get("num_cotas"),
            "fonte": "CVM_INF_MENSAL",
            "arquivo_origem": informe.get("arquivo_origem"),
            "coletado_em": informe.get("coletado_em"),
        }

    except Exception as erro:
        observabilidade.registrar_erro(
            "servicos.cvm_fii_service",
            erro,
            ticker=ticker_norm,
        )
        return None


def calcular_pvp_cvm(ticker: str, preco_mercado: float | None = None) -> dict[str, Any] | None:
    """Calcula P/VP usando VP/cota oficial da CVM e preço de mercado informado ou do banco."""
    ticker_norm = ticker.upper().replace(".SA", "").strip()
    dados = dados_patrimoniais_por_ticker(ticker_norm)
    if not dados:
        return None

    preco = preco_mercado
    if preco is None:
        row = db.buscar_um(
            "SELECT preco FROM indicadores WHERE ticker = ? ORDER BY data DESC LIMIT 1",
            (ticker_norm,),
        )
        preco = row["preco"] if row and row["preco"] is not None else None

    vp_cota = dados.get("valor_patrimonial_cota_cvm")
    if not preco or not vp_cota:
        return {
            **dados,
            "preco_mercado": preco,
            "pvp_cvm": None,
            "status": "INSUFICIENTE_PRECO_OU_VP",
        }

    try:
        pvp = float(preco) / float(vp_cota)
    except Exception:
        pvp = None

    return {
        **dados,
        "preco_mercado": preco,
        "pvp_cvm": round(pvp, 4) if pvp is not None else None,
        "status": "OK" if pvp is not None else "ERRO_CALCULO_PVP",
    }


def comparar_pvp_fundamentus_cvm(ticker: str) -> dict[str, Any] | None:
    """Compara P/VP atual do banco com P/VP recalculado por CVM."""
    ticker_norm = ticker.upper().replace(".SA", "").strip()

    row = db.buscar_um(
        "SELECT preco, pvp FROM indicadores WHERE ticker = ? ORDER BY data DESC LIMIT 1",
        (ticker_norm,),
    )
    if not row:
        return None

    resultado = calcular_pvp_cvm(ticker_norm, row["preco"])
    if not resultado:
        return None

    pvp_atual = row["pvp"]
    pvp_cvm = resultado.get("pvp_cvm")

    divergencia_pct = None
    if pvp_atual is not None and pvp_cvm is not None:
        base = max(abs(float(pvp_atual)), abs(float(pvp_cvm)), 1.0)
        divergencia_pct = abs(float(pvp_atual) - float(pvp_cvm)) / base

    return {
        "ticker": ticker_norm,
        "pvp_atual_banco": pvp_atual,
        "pvp_cvm": pvp_cvm,
        "divergencia_pct": round(divergencia_pct, 4) if divergencia_pct is not None else None,
        "divergente": bool(divergencia_pct is not None and divergencia_pct > 0.02),
        "dados_cvm": resultado,
    }
