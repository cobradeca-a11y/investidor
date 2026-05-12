"""
decisao/gatilhos.py
Gatilhos de gestao de posicao — quando adicionar, reduzir ou sair.

Gatilhos de saida por deterioracao:
  vacancia_fisica > 20%               → REDUZIR
  dy_recorrente cai > 25% em 3 meses → REDUZIR
  score_ia <= 3 por 2 ciclos          → VENDER
  margem negativa > -20%              → VENDER

Gatilhos de realizacao parcial:
  P/VP > 1.20                         → REALIZAR_PARCIAL (30%)
  margem < 0%                         → REALIZAR_PARCIAL (50%)

Gatilhos de adicao:
  preco cai > 10% sem mudanca fundamental → ADICIONAR
  entrada na zona forte                   → ADICIONAR
"""

from typing import Optional
from banco import db
from decisao.zonas_entrada import calcular as calcular_zonas


def verificar(
    ticker: str,
    pvp: Optional[float] = None,
    vacancia: Optional[float] = None,
    margem: Optional[float] = None,
    score_ia: Optional[float] = None,
    dy_recorrente_atual: Optional[float] = None,
) -> dict:
    """
    Verifica todos os gatilhos para o ticker.
    Retorna dict com lista de gatilhos acionados e acao recomendada.
    """
    gatilhos = []

    # ── Gatilhos de saida / reducao ───────────────────────────────────
    if vacancia is not None and vacancia > 20.0:
        gatilhos.append({
            "tipo":    "SAIDA",
            "nome":    "VACANCIA_CRITICA",
            "acao":    "REDUZIR",
            "motivo":  f"Vacancia em {vacancia:.1f}% (limite: 20%). Risco de queda de dividendos.",
        })

    if margem is not None and margem < -0.20:
        gatilhos.append({
            "tipo":    "SAIDA",
            "nome":    "PRECO_MUITO_ACIMA_JUSTO",
            "acao":    "VENDER",
            "motivo":  f"Preco {abs(margem)*100:.1f}% acima do valor justo. Posicao supervalorizou.",
        })

    if score_ia is not None and score_ia <= 3:
        # Verifica se ja foi baixo no ciclo anterior
        ultima = db.buscar_um(
            """
            SELECT score_ia FROM decisoes
            WHERE ticker = ? AND score_ia IS NOT NULL
            ORDER BY data_decisao DESC LIMIT 1
            """,
            (ticker,)
        )
        if ultima and ultima.get('score_ia') and ultima['score_ia'] <= 3:
            gatilhos.append({
                "tipo":    "SAIDA",
                "nome":    "QUALITATIVO_DETERIORADO",
                "acao":    "VENDER",
                "motivo":  f"Score IA <= 3 por 2 ciclos consecutivos. Deterioracao qualitativa confirmada.",
            })

    # ── Gatilhos de realizacao parcial ───────────────────────────────
    if pvp is not None and pvp > 1.20:
        gatilhos.append({
            "tipo":    "REALIZACAO",
            "nome":    "PVP_ELEVADO",
            "acao":    "REALIZAR_PARCIAL_30",
            "motivo":  f"P/VP em {pvp:.2f} (acima de 1.20). Realizar 30% da posicao.",
        })

    if margem is not None and -0.20 <= margem < 0:
        gatilhos.append({
            "tipo":    "REALIZACAO",
            "nome":    "MARGEM_NEGATIVA",
            "acao":    "REALIZAR_PARCIAL_50",
            "motivo":  f"Margem levemente negativa ({margem*100:.1f}%). Realizar 50% da posicao.",
        })

    # ── Gatilhos de adicao ────────────────────────────────────────────
    zonas = calcular_zonas(ticker)
    if zonas.get("calculavel"):
        if zonas["zona_atual"] == "FORTE":
            gatilhos.append({
                "tipo":    "ADICAO",
                "nome":    "ZONA_FORTE",
                "acao":    "ADICIONAR",
                "motivo":  f"Preco na zona de acumulacao forte (R$ {zonas['preco_atual']:.2f} <= R$ {zonas['zona_forte']:.2f}).",
            })

    # Queda de preco sem deterioracao de fundamentos
    queda = _verificar_queda_sem_deterioracao(ticker)
    if queda:
        gatilhos.append({
            "tipo":    "ADICAO",
            "nome":    "QUEDA_SEM_DETERIORACAO",
            "acao":    "ADICIONAR",
            "motivo":  queda,
        })

    # ── Acao consolidada ──────────────────────────────────────────────
    acoes = [g["acao"] for g in gatilhos]
    if "VENDER" in acoes:
        acao_principal = "VENDER"
    elif "REALIZAR_PARCIAL_50" in acoes:
        acao_principal = "REALIZAR_PARCIAL_50"
    elif "REALIZAR_PARCIAL_30" in acoes:
        acao_principal = "REALIZAR_PARCIAL_30"
    elif "REDUZIR" in acoes:
        acao_principal = "REDUZIR"
    elif "ADICIONAR" in acoes:
        acao_principal = "ADICIONAR"
    else:
        acao_principal = "MANTER"

    return {
        "ticker":         ticker,
        "gatilhos":       gatilhos,
        "acao_principal": acao_principal,
        "total_gatilhos": len(gatilhos),
    }


def _verificar_queda_sem_deterioracao(ticker: str) -> Optional[str]:
    """
    Retorna motivo se o preco caiu > 10% mas os fundamentos
    nao deterioraram (vacancia e DY estavel).
    """
    rows = db.buscar_todos(
        """
        SELECT preco, vacancia_fisica, dy_12m FROM indicadores
        WHERE ticker = ?
        ORDER BY data DESC LIMIT 30
        """,
        (ticker,)
    )
    if len(rows) < 10:
        return None

    preco_atual  = rows[0].get('preco')
    preco_antigo = rows[-1].get('preco')
    vac_atual    = rows[0].get('vacancia_fisica')
    vac_antiga   = rows[-1].get('vacancia_fisica')

    if not preco_atual or not preco_antigo or preco_antigo == 0:
        return None

    queda = (preco_atual / preco_antigo - 1)
    if queda > -0.10:
        return None

    # Verifica se vacancia piorou
    if vac_atual and vac_antiga and vac_atual > vac_antiga + 3:
        return None  # deterioracao real

    return (
        f"Preco caiu {abs(queda)*100:.1f}% nos ultimos 30 dias "
        f"sem deterioracao aparente de fundamentos. Oportunidade de adicionar."
    )
