"""
decisao/zonas_entrada.py
Define zonas de entrada concretas em R$ para cada FII.

ZONA_FORTE   = preco_justo * 0.75  (margem > 33%) → comprar sem hesitar
ZONA_PARCIAL = preco_justo * 0.85  (margem > 18%) → comprar 50% da posicao
ZONA_ESPERA  = preco_justo * 0.95  (margem > 5%)  → monitorar, aguardar melhor ponto
FORA_ZONA    = acima da zona de espera             → nao entrar
"""

from typing import Optional
from processamento.margem_seguranca import relatorio_margem


def calcular(ticker: str) -> dict:
    """
    Retorna as zonas de entrada em R$ para o ticker.
    """
    rel = relatorio_margem(ticker)

    if not rel.get("calculavel"):
        return {
            "calculavel":    False,
            "ticker":        ticker,
            "zona_atual":    "INDISPONIVEL",
            "zona_forte":    None,
            "zona_parcial":  None,
            "zona_espera":   None,
            "preco_atual":   None,
            "preco_justo":   None,
        }

    preco_atual = rel["preco_atual"]
    preco_justo = rel["preco_justo"]
    margem      = rel["margem_percentual"]

    zona_forte   = round(preco_justo * 0.75, 2)
    zona_parcial = round(preco_justo * 0.85, 2)
    zona_espera  = round(preco_justo * 0.95, 2)

    # Zona em que o preco atual se encontra
    if preco_atual <= zona_forte:
        zona_atual   = "FORTE"
        acao         = "Preco na zona de acumulacao forte. Comprar sem hesitar."
    elif preco_atual <= zona_parcial:
        zona_atual   = "PARCIAL"
        acao         = "Preco na zona de entrada parcial. Comprar 50% da posicao planejada."
    elif preco_atual <= zona_espera:
        zona_atual   = "ESPERA"
        acao         = f"Preco proximo ao justo. Aguardar recuo para R$ {zona_parcial:.2f}."
    else:
        zona_atual   = "FORA"
        acao         = f"Preco acima do valor justo. Nao entrar. Aguardar R$ {zona_espera:.2f}."

    # Distancia ate a proxima zona
    if zona_atual == "FORA":
        distancia_prox_zona = round((preco_atual / zona_espera - 1) * 100, 1)
        prox_zona_nome = "ESPERA"
        prox_zona_valor = zona_espera
    elif zona_atual == "ESPERA":
        distancia_prox_zona = round((preco_atual / zona_parcial - 1) * 100, 1)
        prox_zona_nome = "PARCIAL"
        prox_zona_valor = zona_parcial
    elif zona_atual == "PARCIAL":
        distancia_prox_zona = round((preco_atual / zona_forte - 1) * 100, 1)
        prox_zona_nome = "FORTE"
        prox_zona_valor = zona_forte
    else:
        distancia_prox_zona = 0.0
        prox_zona_nome = "JA_NA_ZONA_FORTE"
        prox_zona_valor = zona_forte

    return {
        "calculavel":          True,
        "ticker":              ticker,
        "preco_atual":         preco_atual,
        "preco_justo":         round(preco_justo, 2),
        "margem_pct":          round(margem * 100, 1),
        "zona_forte":          zona_forte,
        "zona_parcial":        zona_parcial,
        "zona_espera":         zona_espera,
        "zona_atual":          zona_atual,
        "acao":                acao,
        "prox_zona_nome":      prox_zona_nome,
        "prox_zona_valor":     prox_zona_valor,
        "distancia_prox_zona": distancia_prox_zona,
    }
