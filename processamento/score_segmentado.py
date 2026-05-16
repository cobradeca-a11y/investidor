"""
processamento/score_segmentado.py
Score complementar com pesos por segmento/tipo de FII.

Não substitui os gates eliminatórios. Serve para ranqueamento, explicabilidade e
calibração futura por segmento quando houver amostras suficientes.
"""
from __future__ import annotations

from typing import Any

from config.settings import PESOS_SCORE_SEGMENTADO


def _norm(texto: str | None) -> str:
    return (texto or "").upper().strip()


def chave_segmento(segmento: str | None, tipo: str | None = None) -> str:
    s = _norm(segmento)
    t = _norm(tipo)
    alvo = f"{s} {t}"
    if "PAPEL" in alvo or "RECEB" in alvo or "CRI" in alvo:
        return "PAPEL"
    if "LOG" in alvo:
        return "LOGISTICA"
    if "LAJE" in alvo or "CORPORAT" in alvo or "ESCRIT" in alvo:
        return "LAJES"
    if "SHOP" in alvo:
        return "SHOPPINGS"
    if "HIBR" in alvo or "HÍBR" in alvo:
        return "HIBRIDO"
    return "DEFAULT"


def _score_faixa(valor: float | None, bom: float, ruim: float, maior_melhor: bool = True) -> float:
    if valor is None:
        return 50.0
    valor = float(valor)
    if maior_melhor:
        if valor >= bom:
            return 100.0
        if valor <= ruim:
            return 0.0
        return ((valor - ruim) / (bom - ruim)) * 100
    if valor <= bom:
        return 100.0
    if valor >= ruim:
        return 0.0
    return ((ruim - valor) / (ruim - bom)) * 100


def calcular_score(
    *,
    segmento: str | None,
    tipo: str | None = None,
    dy_recorrente: float | None = None,
    premio_cdi: float | None = None,
    confiabilidade: float | None = None,
    meses_historico: int | None = None,
    pvp: float | None = None,
    vacancia: float | None = None,
    liquidez: float | None = None,
    score_cvm: float | None = None,
) -> dict[str, Any]:
    chave = chave_segmento(segmento, tipo)
    pesos = PESOS_SCORE_SEGMENTADO.get(chave, PESOS_SCORE_SEGMENTADO["DEFAULT"])

    componentes = {
        "dy_recorrente": _score_faixa(dy_recorrente, 0.12, 0.06, True),
        "premio_cdi": _score_faixa(premio_cdi, 3.0, -1.0, True),
        "confiabilidade": float(confiabilidade) if confiabilidade is not None else 50.0,
        "historico": _score_faixa(meses_historico, 60, 12, True),
        "pvp": _score_faixa(pvp, 0.85, 1.20, False),
        "vacancia": _score_faixa(vacancia, 5.0, 20.0, False),
        "liquidez": _score_faixa(liquidez, 2_000_000, 50_000, True),
        "score_cvm": float(score_cvm) if score_cvm is not None else 50.0,
    }

    total_pesos = sum(pesos.values()) or 1
    score = sum(componentes.get(campo, 50.0) * peso for campo, peso in pesos.items()) / total_pesos

    return {
        "score_segmentado": round(score, 2),
        "segmento_score": chave,
        "pesos_usados": pesos,
        "componentes": {k: round(v, 2) for k, v in componentes.items() if k in pesos},
        "calibrado_historicamente": False,
        "motivo_calibracao": "Pesos estáticos por segmento; calibração automática só após amostra mínima definida em settings.",
    }
