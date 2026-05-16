"""
decisao/dimensionamento.py
Calcula o tamanho ideal da posicao para cada FII.

Regras base:
  Margem > 40% + historico > 36m + sem travas  → ate 8% da carteira
  Margem 25-40% ou historico 24-36m            → ate 5% da carteira
  Margem 15-25% ou historico 12-24m            → ate 3% da carteira
  Qualquer trava ativa                         → maximo 2%

O dimensionamento e reduzido pelo semaforo macro:
  VERMELHO → divide por 2
  AMARELO  → divide por 1.5
  VERDE    → sem reducao

Quando valor da carteira e preco da cota sao informados, calcula valor alvo,
quantidade de cotas e lotes de 100. Sem esses dados, nao inventa lotes.
"""

from typing import Optional
from mercado.semaforo_macro import avaliar as avaliar_macro
from mercado.contexto_setorial import score_segmento


def _calcular_quantidade(
    pct_final: float,
    valor_carteira_total: Optional[float],
    preco_cota: Optional[float],
) -> dict:
    if not valor_carteira_total or not preco_cota or valor_carteira_total <= 0 or preco_cota <= 0 or pct_final <= 0:
        return {
            "valor_alvo": None,
            "qtd_cotas": None,
            "lotes_de_100": None,
            "dimensionamento_calculavel": False,
            "motivo_dimensionamento": "Informe valor_carteira_total e preco_cota para calcular quantidade/lotes.",
        }

    valor_alvo = valor_carteira_total * (pct_final / 100)
    qtd_cotas = int(valor_alvo // preco_cota)
    lotes_de_100 = qtd_cotas // 100

    return {
        "valor_alvo": round(valor_alvo, 2),
        "qtd_cotas": qtd_cotas,
        "lotes_de_100": lotes_de_100,
        "valor_estimado_posicao": round(qtd_cotas * preco_cota, 2),
        "dimensionamento_calculavel": True,
        "motivo_dimensionamento": "Quantidade calculada com base no valor real da carteira e preço da cota.",
    }


def calcular(
    ticker: str,
    margem: Optional[float],
    meses_historico: int,
    travas_ativas: list,
    segmento: str,
    score_ia: Optional[float] = None,
    valor_carteira_total: Optional[float] = None,
    preco_cota: Optional[float] = None,
) -> dict:
    """
    Retorna o dimensionamento recomendado para o ativo.

    Output principal:
    {
        "pct_carteira": 5.0,
        "valor_alvo": 5000.00,
        "qtd_cotas": 47,
        "lotes_de_100": 0 | 1 | ... | None,
        "dimensionamento_calculavel": bool,
        "justificativa": str,
    }
    """
    # Base pelo binomio margem + historico
    if margem is None:
        pct_base = 0.0
        motivo_base = "Margem nao calculavel"
    elif margem >= 0.40 and meses_historico >= 36:
        pct_base = 8.0
        motivo_base = f"Margem forte ({margem*100:.1f}%) + historico solido ({meses_historico}m)"
    elif margem >= 0.25 or meses_historico >= 24:
        pct_base = 5.0
        motivo_base = f"Margem boa ({margem*100:.1f}%) ou historico adequado ({meses_historico}m)"
    elif margem >= 0.15 or meses_historico >= 12:
        pct_base = 3.0
        motivo_base = f"Margem moderada ({margem*100:.1f}%) ou historico curto ({meses_historico}m)"
    else:
        pct_base = 1.0
        motivo_base = f"Margem baixa ({margem*100:.1f}%) e historico insuficiente ({meses_historico}m)"

    # Reducao por travas
    reducao_travas = ""
    if travas_ativas:
        pct_base = min(pct_base, 2.0)
        reducao_travas = f"Teto de 2% por travas ativas: {', '.join(travas_ativas[:2])}"

    # Reducao por score IA negativo
    if score_ia is not None and score_ia <= 4:
        pct_base = min(pct_base, 3.0)
        reducao_travas += f" | Score IA baixo ({score_ia}/10)"

    # Ajuste setorial
    ctx_setorial = score_segmento(segmento)
    score_set = ctx_setorial["score"]
    reducao_setorial = ""
    if score_set <= 4:
        pct_base *= 0.6
        reducao_setorial = f"Segmento desfavoravel ({segmento}, score {score_set}/10): -40%"
    elif score_set <= 6:
        pct_base *= 0.8
        reducao_setorial = f"Segmento cauteloso ({segmento}, score {score_set}/10): -20%"

    # Ajuste macro
    macro = avaliar_macro()
    reducao_macro = ""
    if macro["cor"] == "VERMELHO":
        pct_base *= 0.5
        reducao_macro = f"Semaforo VERMELHO ({macro['motivo'][:60]}): -50%"
    elif macro["cor"] == "AMARELO":
        pct_base *= 0.67
        reducao_macro = "Semaforo AMARELO: -33%"

    pct_final = round(max(0, min(10, pct_base)), 1)
    quantidade = _calcular_quantidade(pct_final, valor_carteira_total, preco_cota)

    return {
        "ticker":             ticker.upper().replace(".SA", ""),
        "pct_carteira":       pct_final,
        **quantidade,
        "preco_cota_usado":   preco_cota,
        "valor_carteira_total": valor_carteira_total,
        "motivo_base":        motivo_base,
        "reducao_travas":     reducao_travas,
        "reducao_setorial":   reducao_setorial,
        "reducao_macro":      reducao_macro,
        "semaforo":           macro["cor"],
        "score_setorial":     score_set,
    }
