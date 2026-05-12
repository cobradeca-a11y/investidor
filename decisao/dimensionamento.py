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
"""

from typing import Optional
from mercado.semaforo_macro import avaliar as avaliar_macro
from mercado.contexto_setorial import score_segmento


def calcular(
    ticker: str,
    margem: Optional[float],
    meses_historico: int,
    travas_ativas: list,
    segmento: str,
    score_ia: Optional[float] = None,
) -> dict:
    """
    Retorna o dimensionamento recomendado para o ativo.

    Output:
    {
        "pct_carteira":   5.0,    # % da carteira total
        "lotes_de_100":   5,      # quantos lotes de 100 cotas
        "justificativa":  str,
        "reducao_macro":  str,
        "reducao_setorial": str,
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
        reducao_macro = f"Semaforo AMARELO: -33%"

    pct_final = round(max(0, min(10, pct_base)), 1)
    lotes = max(1, int(pct_final))  # 1 lote por % como referencia inicial

    return {
        "pct_carteira":      pct_final,
        "lotes_de_100":      lotes,
        "motivo_base":       motivo_base,
        "reducao_travas":    reducao_travas,
        "reducao_setorial":  reducao_setorial,
        "reducao_macro":     reducao_macro,
        "semaforo":          macro["cor"],
        "score_setorial":    score_set,
    }
