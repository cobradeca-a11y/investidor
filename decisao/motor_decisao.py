"""
decisao/motor_decisao.py
Motor central de decisão do FIIA.

Recebe todos os dados disponíveis e devolve um veredito padronizado:
    COMPRAR | COMPRAR_PARCIAL | AGUARDAR | MANTER | MONITORAR | EVITAR

Regras:
  - Score da IA é OPCIONAL. Sem IA, o motor decide pelos dados quantitativos.
  - Travas absolutas sempre prevalecem sobre qualquer score.
  - Confiabilidade mínima é pré-requisito para qualquer decisão positiva.
"""

from typing import Optional
from datetime import date

from banco import db
from processamento.confiabilidade import calcular_score as calcular_confiabilidade
from processamento.margem_seguranca import calcular_margem_seguranca
from processamento.dividendo_recorrente import calcular_dy_recorrente, percentual_recorrente
from mercado.comparador_cdi import calcular_premio
from decisao.travas import verificar_travas, status_maximo_permitido


# ─────────────────────────────────────────────────────────────────────────────
# Limiares de decisão
# ─────────────────────────────────────────────────────────────────────────────

_MARGEM_COMPRAR_FORTE   = 0.30   # >30% → COMPRAR
_MARGEM_COMPRAR_PARCIAL = 0.15   # 15-30% → COMPRAR_PARCIAL
_MARGEM_AGUARDAR        = 0.05   # 5-15% → AGUARDAR
# <5% ou negativa → EVITAR / MONITORAR

_SCORE_IA_RISCO_GRAVE   = 4      # score IA ≤ 4 → sobe alerta mesmo com margem boa
_SCORE_IA_BOM           = 7      # score IA ≥ 7 → confirma decisão positiva


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────────────────────

def _meses_historico(ticker: str) -> int:
    row = db.buscar_um(
        "SELECT MIN(data_pagamento) as inicio FROM dividendos WHERE ticker = ?",
        (ticker,)
    )
    if not row or not row["inicio"]:
        return 0
    try:
        inicio = date.fromisoformat(row["inicio"])
        delta  = date.today() - inicio
        return delta.days // 30
    except Exception:
        return 0


def _queda_dividendos_consecutivos(ticker: str) -> int:
    """Conta quantos meses consecutivos o dividendo caiu."""
    rows = db.buscar_todos(
        """
        SELECT valor FROM dividendos
        WHERE ticker = ?
        ORDER BY data_pagamento DESC
        LIMIT 6
        """,
        (ticker,)
    )
    if len(rows) < 2:
        return 0
    valores = [r["valor"] for r in rows]
    consecutivos = 0
    for i in range(len(valores) - 1):
        if valores[i] < valores[i + 1]:
            consecutivos += 1
        else:
            break
    return consecutivos


def _quando_revisar(
    decisao: str,
    margem: Optional[float],
    vacancia: Optional[float],
    tom_gestor: Optional[str],
) -> str:
    if decisao == "COMPRAR":
        return "Revisar se preço subir mais de 20% ou próximo relatório gerencial."
    if decisao == "COMPRAR_PARCIAL":
        return "Revisar em 30 dias ou se preço cair mais 5% (completar posição)."
    if decisao == "AGUARDAR":
        if margem and margem < 0.05:
            return "Monitorar semanalmente. Comprar se preço recuar para a zona de entrada."
        return "Revisar no próximo relatório gerencial ou mudança de preço."
    if decisao == "MONITORAR":
        if tom_gestor == "defensivo":
            return "Aguardar próximo relatório gerencial para reavaliação."
        return "Revisar em 15 dias ou após evento relevante do fundo."
    if decisao == "EVITAR":
        return "Reavaliar somente se preço recuar significativamente ou fundamentos melhorarem."
    return "Revisar no próximo ciclo semanal do radar."


# ─────────────────────────────────────────────────────────────────────────────
# Interface pública
# ─────────────────────────────────────────────────────────────────────────────

def decidir(
    ticker: str,
    score_ia: Optional[float] = None,
    riscos_ia: Optional[list] = None,
    tom_gestor: Optional[str] = None,
    ia_status: str = "INDISPONIVEL",
) -> dict:
    """
    Retorna veredito completo e padronizado para o ticker.

    Parâmetros opcionais (podem ser None se IA indisponível):
      score_ia   : score qualitativo do Gemini (0-10)
      riscos_ia  : lista de riscos identificados pela IA
      tom_gestor : 'otimista' | 'neutro' | 'defensivo' | 'nao_disponivel'
      ia_status  : 'OK' | 'INDISPONIVEL' | 'ERRO' | 'BLOQUEADO_QUOTA'
    """
    ticker = ticker.upper().strip()

    # ── Coleta dados do banco ─────────────────────────────────────────────
    ind      = db.get_by_ticker("indicadores", ticker) or {}
    fii_info = db.get_by_ticker("fiis",        ticker) or {}

    preco      = ind.get("preco")
    pvp        = ind.get("pvp")
    dy_12m     = ind.get("dy_12m")
    liquidez   = ind.get("liquidez_diaria")
    vacancia   = ind.get("vacancia_fisica")
    vpa        = ind.get("vpa")
    segmento   = fii_info.get("segmento", "INDEFINIDO")
    tipo_fundo = fii_info.get("tipo", "INDEFINIDO")

    # ── Cálculos derivados ────────────────────────────────────────────────
    confiabilidade = calcular_confiabilidade(ticker)
    margem         = calcular_margem_seguranca(ticker)
    margem_stress  = calcular_margem_seguranca(ticker, cenario_stress=True)
    dy_recorrente  = calcular_dy_recorrente(ticker, preco) if preco else None
    pct_recorrente = percentual_recorrente(ticker)
    premio_cdi     = calcular_premio(dy_recorrente)
    meses_hist     = _meses_historico(ticker)
    quedas_consec  = _queda_dividendos_consecutivos(ticker)

    preco_justo      = preco * (1 + margem)        if preco and margem is not None else None
    preco_entrada    = preco_justo * 0.95           if preco_justo else None
    preco_stress_val = preco * (1 + margem_stress)  if preco and margem_stress is not None else None

    # ── Travas absolutas ──────────────────────────────────────────────────
    travas = verificar_travas(
        ticker                        = ticker,
        confiabilidade                = confiabilidade,
        liquidez                      = liquidez,
        margem_seguranca              = margem,
        premio_cdi                    = premio_cdi,
        percentual_recorrente         = pct_recorrente,
        tipo_fundo                    = tipo_fundo,
        meses_historico               = meses_hist,
        score_qualidade               = None,
        queda_dividendos_consecutivos = quedas_consec,
    )

    teto = status_maximo_permitido(travas)

    # ── Lógica de decisão quantitativa ────────────────────────────────────
    if margem is None or preco is None:
        decisao_quant = "MONITORAR"
        motivo_quant  = "Dados insuficientes para calcular margem de segurança."
    elif margem >= _MARGEM_COMPRAR_FORTE:
        decisao_quant = "COMPRAR"
        motivo_quant  = f"Margem de segurança expressiva ({margem*100:.1f}%). Preço com desconto relevante ao valor intrínseco."
    elif margem >= _MARGEM_COMPRAR_PARCIAL:
        decisao_quant = "COMPRAR_PARCIAL"
        motivo_quant  = f"Margem positiva ({margem*100:.1f}%), mas ainda há espaço para queda. Entrada parcial reduz risco de timing."
    elif margem >= _MARGEM_AGUARDAR:
        decisao_quant = "AGUARDAR"
        motivo_quant  = f"Margem pequena ({margem*100:.1f}%). Fundo saudável, mas preço não oferece desconto suficiente."
    elif margem >= 0:
        decisao_quant = "AGUARDAR"
        motivo_quant  = f"Margem próxima de zero ({margem*100:.1f}%). Aguardar recuo de preço ou melhora nos fundamentos."
    else:
        decisao_quant = "EVITAR"
        motivo_quant  = f"Margem negativa ({margem*100:.1f}%). Preço acima do valor justo estimado."

    # ── Ajuste por IA (quando disponível) ─────────────────────────────────
    decisao_final = decisao_quant
    ajuste_ia     = None

    if score_ia is not None and ia_status == "OK":
        if score_ia <= _SCORE_IA_RISCO_GRAVE:
            if decisao_final == "COMPRAR":
                decisao_final = "COMPRAR_PARCIAL"
                ajuste_ia = f"IA identificou riscos relevantes (score {score_ia}/10). Reduzindo de COMPRAR para COMPRAR_PARCIAL."
            elif decisao_final == "COMPRAR_PARCIAL":
                decisao_final = "MONITORAR"
                ajuste_ia = f"IA identificou riscos relevantes (score {score_ia}/10). Rebaixando para MONITORAR."

        if tom_gestor == "defensivo" and decisao_final in ("COMPRAR", "COMPRAR_PARCIAL"):
            decisao_final = "AGUARDAR"
            ajuste_ia = "Tom defensivo do gestor no último relatório. Aguardar próximo relatório antes de aportar."

    # ── Aplica teto das travas ────────────────────────────────────────────
    if teto == "MONITORAR" and decisao_final in ("COMPRAR", "COMPRAR_PARCIAL"):
        decisao_final = "MONITORAR"

    # ── Confiança da análise ──────────────────────────────────────────────
    if confiabilidade >= 90 and ia_status == "OK":
        confianca = "ALTA"
    elif confiabilidade >= 75 or ia_status == "OK":
        confianca = "MEDIA"
    else:
        confianca = "BAIXA"

    revisao = _quando_revisar(decisao_final, margem, vacancia, tom_gestor)

    return {
        # Decisão
        "ticker":        ticker,
        "decisao":       decisao_final,
        "motivo":        ajuste_ia or motivo_quant,
        "motivo_quant":  motivo_quant,
        "ajuste_ia":     ajuste_ia,
        "confianca":     confianca,

        # Preços
        "preco_atual":   preco,
        "preco_justo":   round(preco_justo, 2)      if preco_justo      else None,
        "preco_entrada": round(preco_entrada, 2)    if preco_entrada    else None,
        "preco_stress":  round(preco_stress_val, 2) if preco_stress_val else None,

        # Indicadores
        "margem":            round(margem * 100, 1)        if margem is not None     else None,
        "margem_stress":     round(margem_stress * 100, 1) if margem_stress is not None else None,
        "pvp":               pvp,
        "dy_12m_pct":        round(dy_12m * 100, 2)        if dy_12m                 else None,
        "dy_recorrente_pct": round(dy_recorrente * 100, 2) if dy_recorrente          else None,
        "pct_recorrente":    round(pct_recorrente * 100, 1) if pct_recorrente        else None,
        "premio_cdi":        round(premio_cdi, 2)           if premio_cdi is not None else None,
        "vacancia":          vacancia,
        "liquidez":          liquidez,
        "segmento":          segmento,

        # Qualidade e governança
        "confiabilidade":  confiabilidade,
        "meses_historico": meses_hist,
        "travas":          [t["nome"] for t in travas if t["bloqueia_entrada"]],
        "alertas":         [t["motivo"] for t in travas],

        # IA
        "score_ia":   score_ia,
        "riscos_ia":  riscos_ia or [],
        "tom_gestor": tom_gestor or "nao_disponivel",
        "ia_status":  ia_status,

        # Metadados
        "revisao":       revisao,
        "data_analise":  date.today().isoformat(),
        "versao_modelo": "2.0",
    }
