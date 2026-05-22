"""
processamento/modelos_valuation.py
Modelos concorrentes de valuation para laboratorio historico.

Este modulo nao decide compra. Ele apenas calcula precos justos/precos-teto
com premissas explicitas para permitir backtest A/B sem alterar o motor.
"""
from __future__ import annotations

from statistics import median
from typing import Any


_TAXA_MINIMA_GORDON = 0.01
_YIELD_BAZIN_FIXO = 0.06
_PREMIO_CDI_PADRAO = 0.01

_CRESCIMENTO_SEGMENTO = {
    "LOGISTICA": 0.040,
    "LOGÍSTICA": 0.040,
    "LAJES": 0.030,
    "CORPORATIVO": 0.030,
    "ESCRITORIO": 0.030,
    "ESCRITÓRIO": 0.030,
    "SHOPPING": 0.035,
    "SHOPPINGS": 0.035,
    "RESIDENCIAL": 0.040,
    "HIBRIDO": 0.025,
    "HÍBRIDO": 0.025,
}


def _numero(valor: Any) -> float | None:
    if valor is None or valor == "":
        return None
    try:
        numero = float(valor)
    except Exception:
        return None
    return numero


def _taxa_decimal(valor: Any) -> float | None:
    numero = _numero(valor)
    if numero is None:
        return None
    return numero / 100.0 if numero > 1 else numero


def _segmento(contexto: dict[str, Any]) -> str:
    return str(contexto.get("segmento") or "").upper()


def _eh_papel(contexto: dict[str, Any]) -> bool:
    seg = _segmento(contexto)
    return "PAPEL" in seg or "RECEB" in seg or "CRI" in seg


def _crescimento(contexto: dict[str, Any]) -> float:
    seg = _segmento(contexto)
    for chave, valor in _CRESCIMENTO_SEGMENTO.items():
        if chave in seg:
            return valor
    return 0.0


def _preco(contexto: dict[str, Any]) -> float | None:
    return _numero(contexto.get("preco") or contexto.get("preco_atual"))


def _vpa(contexto: dict[str, Any]) -> float | None:
    return _numero(contexto.get("vpa") or contexto.get("valor_patrimonial_cota"))


def _dividendo_anual_recorrente(contexto: dict[str, Any]) -> float | None:
    preco = _preco(contexto)
    dy_recorrente = _taxa_decimal(contexto.get("dy_recorrente") or contexto.get("dy_12m"))
    ultimo = _numero(contexto.get("ultimo_dividendo"))

    if preco and dy_recorrente is not None and dy_recorrente > 0:
        return preco * dy_recorrente
    if ultimo and ultimo > 0:
        return ultimo * 12
    return None


def _cdi(contexto: dict[str, Any]) -> float:
    return _taxa_decimal(contexto.get("cdi_atual")) or 0.0


def _taxa_desconto(contexto: dict[str, Any]) -> float:
    selic = _taxa_decimal(contexto.get("selic_atual"))
    ipca = _taxa_decimal(contexto.get("ipca_atual"))
    candidatos = []
    if selic is not None:
        candidatos.append(selic + 0.01)
    if ipca is not None:
        candidatos.append(ipca + 0.08)
    return max(candidatos) if candidatos else 0.12


def _resultado(
    *,
    modelo: str,
    aplicavel: bool,
    preco_justo: float | None,
    contexto: dict[str, Any],
    premissas: dict[str, Any],
    motivo: str,
) -> dict[str, Any]:
    preco_atual = _preco(contexto)
    margem = None
    if aplicavel and preco_atual and preco_justo:
        margem = (preco_justo / preco_atual) - 1

    return {
        "modelo": modelo,
        "aplicavel": bool(aplicavel),
        "preco_atual": round(preco_atual, 2) if preco_atual is not None else None,
        "preco_justo": round(preco_justo, 2) if preco_justo is not None else None,
        "margem": round(margem, 4) if margem is not None else None,
        "margem_pct": round(margem * 100, 2) if margem is not None else None,
        "premissas": premissas,
        "motivo": motivo,
    }


def modelo_bazin_barsi_fixo(contexto: dict[str, Any]) -> dict[str, Any]:
    """Preco-teto por dividendos recorrentes usando yield fixo de 6% a.a."""
    dividendo = _dividendo_anual_recorrente(contexto)
    preco_justo = (dividendo / _YIELD_BAZIN_FIXO) if dividendo else None
    return _resultado(
        modelo="BAZIN_BARSI_6",
        aplicavel=preco_justo is not None,
        preco_justo=preco_justo,
        contexto=contexto,
        premissas={"yield_exigido": _YIELD_BAZIN_FIXO, "dividendo_anual_recorrente": dividendo},
        motivo="Preco-teto por dividendo recorrente anual dividido por yield fixo de 6%.",
    )


def modelo_bazin_barsi_cdi(contexto: dict[str, Any], premio_cdi: float = _PREMIO_CDI_PADRAO) -> dict[str, Any]:
    """Preco-teto por dividendos exigindo max(6%, CDI + premio)."""
    dividendo = _dividendo_anual_recorrente(contexto)
    yield_exigido = max(_YIELD_BAZIN_FIXO, _cdi(contexto) + premio_cdi)
    preco_justo = (dividendo / yield_exigido) if dividendo and yield_exigido > 0 else None
    return _resultado(
        modelo="BAZIN_BARSI_CDI",
        aplicavel=preco_justo is not None,
        preco_justo=preco_justo,
        contexto=contexto,
        premissas={
            "yield_exigido": yield_exigido,
            "cdi": _cdi(contexto),
            "premio_cdi": premio_cdi,
            "dividendo_anual_recorrente": dividendo,
        },
        motivo="Preco-teto por dividendo recorrente com yield minimo dinamico contra CDI.",
    )


def modelo_gordon(contexto: dict[str, Any]) -> dict[str, Any]:
    """Dividend Discount Model/Gordon para fluxo recorrente."""
    dividendo = _dividendo_anual_recorrente(contexto)
    taxa = _taxa_desconto(contexto)
    crescimento = 0.0 if _eh_papel(contexto) else _crescimento(contexto)
    taxa_efetiva = max(taxa - crescimento, _TAXA_MINIMA_GORDON)
    preco_justo = (dividendo / taxa_efetiva) if dividendo else None
    return _resultado(
        modelo="GORDON_DDM",
        aplicavel=preco_justo is not None,
        preco_justo=preco_justo,
        contexto=contexto,
        premissas={
            "taxa_desconto": taxa,
            "crescimento": crescimento,
            "taxa_efetiva": taxa_efetiva,
            "dividendo_anual_recorrente": dividendo,
        },
        motivo="Fluxo anual recorrente descontado por taxa dinamica menos crescimento estimado.",
    )


def modelo_pvp(contexto: dict[str, Any]) -> dict[str, Any]:
    """Referencia patrimonial por VPA, sem chamar VPA de garantia de valor justo."""
    vpa = _vpa(contexto)
    alvo = 1.00 if not _eh_papel(contexto) else 0.98
    preco_justo = vpa * alvo if vpa else None
    return _resultado(
        modelo="PVP_CVM",
        aplicavel=preco_justo is not None,
        preco_justo=preco_justo,
        contexto=contexto,
        premissas={"vpa": vpa, "pvp_alvo": alvo, "fonte_patrimonial": contexto.get("patrimonio_fonte")},
        motivo="Referencia por valor patrimonial por cota ajustado por P/VP alvo.",
    )


def aplicar_modelos_valuation(contexto: dict[str, Any]) -> dict[str, Any]:
    """Aplica modelos concorrentes e retorna comparacao auditavel."""
    modelos = [
        modelo_bazin_barsi_fixo(contexto),
        modelo_bazin_barsi_cdi(contexto),
        modelo_gordon(contexto),
        modelo_pvp(contexto),
    ]
    aplicaveis = [m for m in modelos if m.get("aplicavel") and m.get("preco_justo")]
    precos = [float(m["preco_justo"]) for m in aplicaveis]
    conservador = min(precos) if precos else None
    mediano = median(precos) if precos else None

    composto = _resultado(
        modelo="COMPOSTO_CONSERVADOR",
        aplicavel=conservador is not None,
        preco_justo=conservador,
        contexto=contexto,
        premissas={
            "metodo": "minimo_dos_modelos_aplicaveis",
            "preco_mediano_modelos": round(mediano, 2) if mediano is not None else None,
            "modelos_aplicaveis": [m["modelo"] for m in aplicaveis],
        },
        motivo="Usa o menor preco justo entre modelos aplicaveis para reduzir otimismo.",
    )

    return {
        "ticker": contexto.get("ticker"),
        "data_referencia": contexto.get("data_referencia") or contexto.get("data"),
        "segmento": contexto.get("segmento"),
        "modelos": modelos,
        "composto_conservador": composto,
    }
