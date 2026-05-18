"""
mercado/contexto_setorial.py
Score setorial para cada segmento de FII no momento macro atual.

Cada segmento responde a drivers economicos diferentes:
  PAPEL      → curva de juros (IPCA+, CDI+)
  LOGISTICA  → atividade economica e e-commerce
  LAJES      → desemprego e absorcao corporativa
  SHOPPINGS  → consumo das familias
  HIBRIDO    → media ponderada

Score 0-10: 10 = melhor momento possivel para o segmento
"""

from typing import Optional
from coleta.api_bcb import obter_selic_atual, obter_ipca_atual
from mercado.semaforo_macro import tendencia_selic


# Pesos de sensibilidade por segmento
# (selic_hostil, selic_queda, ipca_alto, ipca_baixo)
_SENSIBILIDADE = {
    "PAPEL":      {"selic_hostil": +2, "selic_queda": -1, "ipca_alto": +2, "ipca_baixo": -1},
    "LOGISTICA":  {"selic_hostil": -2, "selic_queda": +2, "ipca_alto": -1, "ipca_baixo": +1},
    "LAJES":      {"selic_hostil": -2, "selic_queda": +2, "ipca_alto": -1, "ipca_baixo": +1},
    "SHOPPINGS":  {"selic_hostil": -1, "selic_queda": +1, "ipca_alto": -2, "ipca_baixo": +2},
    "HIBRIDO":    {"selic_hostil": -1, "selic_queda": +1, "ipca_alto":  0, "ipca_baixo":  0},
    "RESIDENCIAL":{"selic_hostil": -2, "selic_queda": +2, "ipca_alto": -1, "ipca_baixo": +1},
    "HOTEL":      {"selic_hostil": -1, "selic_queda": +1, "ipca_alto": -1, "ipca_baixo": +1},
    "EDUCACIONAL":{"selic_hostil": -1, "selic_queda": +1, "ipca_alto":  0, "ipca_baixo":  0},
    "INDEFINIDO": {"selic_hostil":  0, "selic_queda":  0, "ipca_alto":  0, "ipca_baixo":  0},
}

_SELIC_HOSTIL_LIMIAR = 13.0
_IPCA_ALTO_LIMIAR    = 6.0
_BASE_SCORE          = 6  # score neutro


def _normalizar_segmento(segmento: str) -> str:
    s = segmento.upper()
    if any(x in s for x in ['PAPEL', 'RECEBIVEL', 'CREDITO', 'CRI']):
        return "PAPEL"
    if any(x in s for x in ['LOGIS', 'GALPAO', 'INDUSTRIAL']):
        return "LOGISTICA"
    if any(x in s for x in ['LAJE', 'ESCRITORIO', 'CORPORATIV']):
        return "LAJES"
    if any(x in s for x in ['SHOPPING', 'VAREJO', 'RETAIL']):
        return "SHOPPINGS"
    if any(x in s for x in ['HOTEL', 'HOSPIT']):
        return "HOTEL"
    if any(x in s for x in ['RESID', 'HABITAC']):
        return "RESIDENCIAL"
    if any(x in s for x in ['EDUC', 'UNIVER', 'ESCOLA']):
        return "EDUCACIONAL"
    if 'HIBRIDO' in s or 'MULTI' in s or 'DIVERSIF' in s:
        return "HIBRIDO"
    return "INDEFINIDO"


def score_segmento(segmento: str, contexto: Optional[dict] = None) -> dict:
    """
    Retorna score setorial (0-10) e justificativa para o segmento.
    """
    seg_norm  = _normalizar_segmento(segmento)
    pesos     = _SENSIBILIDADE.get(seg_norm, _SENSIBILIDADE["INDEFINIDO"])

    if contexto:
        selic = contexto.get("selic_atual") or 10.0
        ipca = contexto.get("ipca_atual") or 4.0
        macro = contexto.get("semaforo_macro") or {}
        tendencia = macro.get("tendencia") or "ESTAVEL"
    else:
        selic     = obter_selic_atual() or 10.0
        ipca      = obter_ipca_atual()  or 4.0
        tendencia = tendencia_selic()


    score = _BASE_SCORE

    # Ajuste por SELIC
    if selic >= _SELIC_HOSTIL_LIMIAR:
        score += pesos["selic_hostil"]
    elif tendencia == "QUEDA":
        score += pesos["selic_queda"]

    # Ajuste por IPCA
    if ipca >= _IPCA_ALTO_LIMIAR:
        score += pesos["ipca_alto"]
    else:
        score += pesos["ipca_baixo"]

    # Ajuste por tendencia da SELIC
    if tendencia == "ALTA":
        score -= 1
    elif tendencia == "QUEDA":
        score += 1

    score = max(0, min(10, score))

    # Classificacao
    if score >= 8:
        classificacao = "FAVORAVEL"
    elif score >= 6:
        classificacao = "NEUTRO"
    elif score >= 4:
        classificacao = "CAUTELOSO"
    else:
        classificacao = "DESFAVORAVEL"

    return {
        "segmento":       segmento,
        "segmento_norm":  seg_norm,
        "score":          score,
        "classificacao":  classificacao,
        "selic":          selic,
        "ipca":           ipca,
        "tendencia_selic": tendencia,
    }


def todos_segmentos() -> list[dict]:
    """Retorna score de todos os segmentos ordenado do melhor ao pior."""
    segmentos = list(_SENSIBILIDADE.keys())
    scores = [score_segmento(s) for s in segmentos if s != "INDEFINIDO"]
    return sorted(scores, key=lambda x: x["score"], reverse=True)
