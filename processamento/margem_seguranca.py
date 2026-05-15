"""
processamento/margem_seguranca.py
Calcula o preço justo e a margem de segurança de um FII.

Regra atual:
  - preço vem da base de indicadores;
  - VP/Cota e P/VP passam pelo resolvedor patrimonial CVM-first;
  - Fundamentus/banco atual fica apenas como fallback rastreável.
"""
from typing import Optional

from banco import db
from coleta import api_bcb
from processamento.dividendo_recorrente import calcular_dy_recorrente
from servicos.resolvedor_patrimonial import resolver_patrimonio

_SELIC_FALLBACK = 10.75  # usado somente se BCB e base local falharem


def _taxa_desconto() -> float:
    """Taxa de desconto dinâmica: MAX(IPCA + 8%, SELIC + 1%)."""
    ipca = api_bcb.obter_ipca_atual() or 4.5
    selic = api_bcb.obter_selic_atual() or _SELIC_FALLBACK
    return max((ipca / 100.0) + 0.08, (selic / 100.0) + 0.01)


def _buscar_segmento(ticker: str) -> str | None:
    fii_info = db.buscar_um("SELECT segmento FROM fiis WHERE ticker = ?", (ticker,))
    return fii_info["segmento"].upper() if fii_info and fii_info["segmento"] else None


def _dados_base_margem(ticker: str) -> dict:
    """Resolve preço, VP/Cota e fonte patrimonial para o cálculo de margem."""
    ticker_norm = ticker.upper().replace(".SA", "").strip()
    patrimonio = resolver_patrimonio(ticker_norm)
    segmento = _buscar_segmento(ticker_norm)

    preco = patrimonio.get("preco")
    vpa = patrimonio.get("valor_patrimonial_cota")

    return {
        "ticker": ticker_norm,
        "preco": preco,
        "vpa": vpa,
        "pvp": patrimonio.get("pvp"),
        "segmento": segmento,
        "fonte_patrimonial": patrimonio.get("fonte_patrimonial"),
        "usou_cvm": patrimonio.get("usou_cvm"),
        "fallback_usado": patrimonio.get("fallback_usado"),
        "competencia_cvm": patrimonio.get("competencia_cvm"),
    }


def calcular_margem_seguranca(ticker: str, cenario_stress: bool = False) -> Optional[float]:
    """
    Motor quantitativo com macrocorrelação e stress test.

    Retorna a margem de segurança em decimal.
    Exemplo: 0.12 = +12%.
    """
    base = _dados_base_margem(ticker)

    if not base["preco"] or not base["vpa"] or not base["segmento"]:
        return None

    preco_atual = float(base["preco"])
    vpa = float(base["vpa"])
    segmento = base["segmento"]
    taxa_desconto_exigida = _taxa_desconto()

    if "PAPEL" in segmento or "RECEBÍVEIS" in segmento or "RECEBIVEIS" in segmento:
        premio_vpa = 1.02 if not cenario_stress else 0.95
        preco_justo = vpa * premio_vpa
    else:
        dy_anual = calcular_dy_recorrente(base["ticker"], preco_atual)
        if dy_anual is None:
            preco_justo = vpa * (0.90 if not cenario_stress else 0.75)
        else:
            fluxo_anual = dy_anual * preco_atual
            if cenario_stress:
                fluxo_anual *= 0.85
            preco_justo = fluxo_anual / taxa_desconto_exigida

    margem = (preco_justo / preco_atual) - 1
    return round(margem, 4)


def relatorio_margem(ticker: str) -> dict:
    """Retorna relatório completo de valuation para exibição no CLI/API."""
    base = _dados_base_margem(ticker)

    if not base["preco"] or not base["vpa"] or not base["segmento"]:
        return {
            "calculavel": False,
            "ticker": base.get("ticker"),
            "fonte_patrimonial": base.get("fonte_patrimonial"),
            "usou_cvm": base.get("usou_cvm"),
            "fallback_usado": base.get("fallback_usado"),
        }

    preco_atual = float(base["preco"])
    vpa = float(base["vpa"])
    segmento = base["segmento"]

    margem = calcular_margem_seguranca(base["ticker"])
    margem_stress = calcular_margem_seguranca(base["ticker"], cenario_stress=True)

    if margem is None or margem_stress is None:
        return {
            "calculavel": False,
            "ticker": base.get("ticker"),
            "fonte_patrimonial": base.get("fonte_patrimonial"),
            "usou_cvm": base.get("usou_cvm"),
            "fallback_usado": base.get("fallback_usado"),
        }

    preco_justo = preco_atual * (1 + margem)
    preco_stress = preco_atual * (1 + margem_stress)
    avaliacao = "POSITIVA" if margem > 0 else "NEGATIVA"
    taxa_desconto = _taxa_desconto()
    dy_anual = (
        calcular_dy_recorrente(base["ticker"], preco_atual)
        if "PAPEL" not in segmento and "RECEBÍVEIS" not in segmento and "RECEBIVEIS" not in segmento
        else None
    )

    return {
        "calculavel": True,
        "ticker": base["ticker"],
        "preco_atual": preco_atual,
        "vpa_utilizado": vpa,
        "pvp_utilizado": base.get("pvp"),
        "fonte_patrimonial": base.get("fonte_patrimonial"),
        "usou_cvm": base.get("usou_cvm"),
        "fallback_usado": base.get("fallback_usado"),
        "competencia_cvm": base.get("competencia_cvm"),
        "preco_justo": preco_justo,
        "preco_stress": preco_stress,
        "margem_percentual": margem,
        "margem_stress": margem_stress,
        "avaliacao": avaliacao,
        "segmento": segmento,
        "dy_anual": dy_anual,
        "taxa_desconto": taxa_desconto,
    }
