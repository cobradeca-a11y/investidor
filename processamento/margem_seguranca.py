"""
processamento/margem_seguranca.py
Calcula o preço justo e a margem de segurança de um FII.

Correção aplicada:
  - SELIC agora vem do banco (api_bcb.obter_selic_atual) com fallback 10.75
"""
from typing import Optional
from banco import db
from coleta import api_bcb
from processamento.dividendo_recorrente import calcular_dy_recorrente

_SELIC_FALLBACK = 10.75  # usado somente se o BCB falhar


def _taxa_desconto() -> float:
    """Taxa de desconto dinâmica: MAX(IPCA + 8%, SELIC + 1%)."""
    ipca  = api_bcb.obter_ipca_atual()  or 4.5
    selic = api_bcb.obter_selic_atual() or _SELIC_FALLBACK  # FIX: dinâmico
    return max((ipca / 100.0) + 0.08, (selic / 100.0) + 0.01)


def calcular_margem_seguranca(ticker: str, cenario_stress: bool = False) -> Optional[float]:
    """
    Motor Quantitativo com Macro-Correlação e Stress Test.
    Retorna a margem de segurança (decimal). Ex: 0.12 = +12%.
    """
    ind = db.buscar_um(
        "SELECT preco, vpa FROM indicadores WHERE ticker = ? ORDER BY data DESC LIMIT 1",
        (ticker,)
    )
    fii_info = db.buscar_um("SELECT segmento FROM fiis WHERE ticker = ?", (ticker,))

    if not ind or not ind["preco"] or not ind["vpa"] or not fii_info:
        return None

    preco_atual = ind["preco"]
    vpa         = ind["vpa"]
    segmento    = fii_info["segmento"].upper()

    taxa_desconto_exigida = _taxa_desconto()

    if "PAPEL" in segmento or "RECEBÍVEIS" in segmento:
        # Fundo de Papel: valuation por P/VP
        premio_vpa = 1.02 if not cenario_stress else 0.95
        preco_justo = vpa * premio_vpa
    else:
        # Fundo de Tijolo: valuation por fluxo de caixa
        dy_anual = calcular_dy_recorrente(ticker, preco_atual)
        if dy_anual is None:
            preco_justo = vpa * (0.90 if not cenario_stress else 0.75)
        else:
            fluxo_anual = dy_anual * preco_atual
            if cenario_stress:
                fluxo_anual *= 0.85  # stress: -15% de receita
            preco_justo = fluxo_anual / taxa_desconto_exigida

    margem = (preco_justo / preco_atual) - 1
    return round(margem, 4)


def relatorio_margem(ticker: str) -> dict:
    """Retorna relatório completo de valuation para exibição no CLI."""
    ind = db.buscar_um(
        "SELECT preco, vpa FROM indicadores WHERE ticker = ? ORDER BY data DESC LIMIT 1",
        (ticker,)
    )
    fii_info = db.buscar_um("SELECT segmento FROM fiis WHERE ticker = ?", (ticker,))

    if not ind or not ind["preco"] or not ind["vpa"] or not fii_info:
        return {"calculavel": False}

    preco_atual = ind["preco"]
    segmento    = fii_info["segmento"].upper()

    margem        = calcular_margem_seguranca(ticker)
    margem_stress = calcular_margem_seguranca(ticker, cenario_stress=True)

    if margem is None or margem_stress is None:
        return {"calculavel": False}

    preco_justo  = preco_atual * (1 + margem)
    preco_stress = preco_atual * (1 + margem_stress)
    avaliacao    = "POSITIVA" if margem > 0 else "NEGATIVA"

    taxa_desconto = _taxa_desconto()
    dy_anual = (
        calcular_dy_recorrente(ticker, preco_atual)
        if "PAPEL" not in segmento and "RECEBÍVEIS" not in segmento
        else None
    )

    return {
        "calculavel":       True,
        "preco_atual":      preco_atual,
        "preco_justo":      preco_justo,
        "preco_stress":     preco_stress,
        "margem_percentual": margem,
        "avaliacao":        avaliacao,
        "segmento":         segmento,
        "dy_anual":         dy_anual,
        "taxa_desconto":    taxa_desconto,
    }
