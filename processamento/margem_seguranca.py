"""
processamento/margem_seguranca.py
Calcula o preço justo e a margem de segurança de um FII.

Regra atual:
  - preço vem da base de indicadores;
  - VP/Cota e P/VP passam pelo resolvedor patrimonial CVM-first;
  - Fundamentus/banco atual fica apenas como fallback rastreável;
  - fundos de tijolo usam Gordon com crescimento contratual estimado por segmento.
"""
from typing import Optional

from banco import db
from coleta import api_bcb
from processamento.dividendo_recorrente import calcular_dy_recorrente
from servicos.resolvedor_patrimonial import resolver_patrimonio

_SELIC_FALLBACK = 10.75  # usado somente se BCB e base local falharem
_TAXA_EFETIVA_MINIMA = 0.01

_CRESCIMENTO_CONTRATUAL_SEGMENTO = {
    "LOGISTICA": 0.040,
    "LOGÍSTICA": 0.040,
    "LAJES": 0.030,
    "CORPORATIVO": 0.030,
    "ESCRITORIO": 0.030,
    "ESCRITÓRIO": 0.030,
    "SHOPPING": 0.035,
    "SHOPPINGS": 0.035,
    "RESIDENCIAL": 0.040,
    "RENDA_URBANA": 0.035,
    "RENDA URBANA": 0.035,
    "URBANA": 0.035,
    "HÍBRIDO": 0.025,
    "HIBRIDO": 0.025,
}


def _taxa_desconto(contexto: Optional[dict] = None) -> float:
    """Taxa de desconto dinâmica: MAX(IPCA + 8%, SELIC + 1%)."""
    if contexto:
        ipca = contexto.get("ipca_atual")
        selic = contexto.get("selic_atual")
        if ipca is None or selic is None:
            raise ValueError("IPCA ou SELIC ausente no contexto.")
    else:
        ipca = api_bcb.obter_ipca_atual() or 4.5
        selic = api_bcb.obter_selic_atual() or _SELIC_FALLBACK
    return max((ipca / 100.0) + 0.08, (selic / 100.0) + 0.01)


def _buscar_segmento(ticker: str) -> str | None:
    fii_info = db.buscar_um("SELECT segmento FROM fiis WHERE ticker = ?", (ticker,))
    return fii_info["segmento"].upper() if fii_info and fii_info["segmento"] else None


def _eh_papel(segmento: str | None) -> bool:
    segmento_norm = (segmento or "").upper()
    return "PAPEL" in segmento_norm or "RECEBÍVEIS" in segmento_norm or "RECEBIVEIS" in segmento_norm


def _crescimento_contratual(segmento: str | None, cenario_stress: bool = False) -> float:
    """
    Retorna crescimento contratual anual estimado para fundos de tijolo.

    Conservador por desenho: no stress, o crescimento considerado é cortado pela metade.
    Segmentos não mapeados usam crescimento zero, preservando prudência.
    """
    segmento_norm = (segmento or "").upper()
    crescimento = 0.0
    for chave, valor in _CRESCIMENTO_CONTRATUAL_SEGMENTO.items():
        if chave in segmento_norm:
            crescimento = valor
            break
    return crescimento * 0.5 if cenario_stress else crescimento




def _fator_patrimonial_por_vacancia(contexto: Optional[dict] = None) -> float:
    """Ajusta o VPA conforme risco operacional visível por vacância."""
    vacancia = None
    if contexto:
        vacancia = contexto.get("vacancia_fisica")
    try:
        vacancia = float(vacancia) if vacancia is not None else None
    except Exception:
        vacancia = None

    if vacancia is None:
        return 0.90
    if vacancia <= 0.03:
        return 0.98
    if vacancia <= 0.08:
        return 0.95
    if vacancia <= 0.15:
        return 0.90
    return 0.80


def _pesos_valor_hibrido(segmento: str | None) -> tuple[float, float]:
    """Define pesos renda/patrimônio por segmento de FII de tijolo."""
    segmento_norm = (segmento or "").upper()
    if "LOGÍSTICA" in segmento_norm or "LOGISTICA" in segmento_norm:
        return 0.60, 0.40
    if "SHOPPING" in segmento_norm:
        return 0.60, 0.40
    if "RENDA_URBANA" in segmento_norm or "RENDA URBANA" in segmento_norm or "URBANA" in segmento_norm:
        return 0.55, 0.45
    if "LAJES" in segmento_norm or "CORPORATIVO" in segmento_norm or "ESCRITORIO" in segmento_norm or "ESCRITÓRIO" in segmento_norm:
        return 0.65, 0.35
    if "HÍBRIDO" in segmento_norm or "HIBRIDO" in segmento_norm:
        return 0.65, 0.35
    return 0.70, 0.30


def _valor_patrimonial_ajustado(vpa: float, contexto: Optional[dict] = None) -> float:
    return float(vpa) * _fator_patrimonial_por_vacancia(contexto)


def _valor_hibrido_tijolo(valor_renda: float, vpa: float, segmento: str | None, contexto: Optional[dict] = None) -> float:
    peso_renda, peso_patrimonio = _pesos_valor_hibrido(segmento)
    valor_patrimonial = _valor_patrimonial_ajustado(vpa, contexto)
    return (float(valor_renda) * peso_renda) + (valor_patrimonial * peso_patrimonio)

def _dados_base_margem(ticker: str, contexto: Optional[dict] = None) -> dict:
    """Resolve preço, VP/Cota e fonte patrimonial para o cálculo de margem."""
    ticker_norm = ticker.upper().replace(".SA", "").strip()
    if contexto:
        return {
            "ticker": ticker_norm,
            "preco": contexto.get("preco"),
            "vpa": contexto.get("vpa"),
            "pvp": contexto.get("pvp"),
            "segmento": contexto.get("segmento"),
            "fonte_patrimonial": contexto.get("patrimonio_fonte"),
            "usou_cvm": contexto.get("patrimonio_fonte") == "CVM_INF_MENSAL",
            "fallback_usado": contexto.get("patrimonio_fonte") != "CVM_INF_MENSAL",
            "competencia_cvm": contexto.get("competencia_patrimonial"),
        }

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


def _preco_justo(base: dict, cenario_stress: bool = False, contexto: Optional[dict] = None) -> float | None:
    preco_atual = float(base["preco"])
    vpa = float(base["vpa"])
    segmento = base["segmento"]
    taxa_desconto_exigida = _taxa_desconto(contexto)

    if _eh_papel(segmento):
        premio_vpa = 1.02 if not cenario_stress else 0.95
        return vpa * premio_vpa

    dy_anual = calcular_dy_recorrente(base["ticker"], preco_atual, contexto=contexto)
    if dy_anual is None:
        return vpa * (0.90 if not cenario_stress else 0.75)

    fluxo_anual = dy_anual * preco_atual
    if cenario_stress:
        fluxo_anual *= 0.85

    crescimento = _crescimento_contratual(segmento, cenario_stress=cenario_stress)
    taxa_efetiva = taxa_desconto_exigida - crescimento
    if taxa_efetiva <= 0:
        taxa_efetiva = _TAXA_EFETIVA_MINIMA

    valor_renda = fluxo_anual / taxa_efetiva
    return _valor_hibrido_tijolo(valor_renda, vpa, segmento, contexto)


def calcular_margem_seguranca(ticker: str, cenario_stress: bool = False, contexto: Optional[dict] = None) -> Optional[float]:
    """
    Motor quantitativo com macrocorrelação e stress test.

    Retorna a margem de segurança em decimal.
    Exemplo: 0.12 = +12%.
    """
    base = _dados_base_margem(ticker, contexto)

    if not base["preco"] or not base["vpa"] or not base["segmento"]:
        return None

    preco_atual = float(base["preco"])
    preco_justo = _preco_justo(base, cenario_stress=cenario_stress, contexto=contexto)
    if preco_justo is None:
        return None

    margem = (preco_justo / preco_atual) - 1
    return round(margem, 4)


def relatorio_margem(ticker: str, contexto: Optional[dict] = None) -> dict:
    """Retorna relatório completo de valuation para exibição no CLI/API."""
    base = _dados_base_margem(ticker, contexto)

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

    margem = calcular_margem_seguranca(base["ticker"], contexto=contexto)
    margem_stress = calcular_margem_seguranca(base["ticker"], cenario_stress=True, contexto=contexto)

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
    taxa_desconto = _taxa_desconto(contexto)
    crescimento_contratual = 0.0 if _eh_papel(segmento) else _crescimento_contratual(segmento)
    crescimento_contratual_stress = 0.0 if _eh_papel(segmento) else _crescimento_contratual(segmento, cenario_stress=True)
    taxa_efetiva = max(taxa_desconto - crescimento_contratual, _TAXA_EFETIVA_MINIMA)
    taxa_efetiva_stress = max(taxa_desconto - crescimento_contratual_stress, _TAXA_EFETIVA_MINIMA)
    dy_anual = (
        calcular_dy_recorrente(base["ticker"], preco_atual, contexto=contexto)
        if not _eh_papel(segmento)
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
        "crescimento_contratual": crescimento_contratual,
        "crescimento_contratual_stress": crescimento_contratual_stress,
        "taxa_efetiva_gordon": taxa_efetiva,
        "taxa_efetiva_gordon_stress": taxa_efetiva_stress,
    }

