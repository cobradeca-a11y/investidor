"""
decisao/motor_decisao.py
Motor central de decisão do FIIA - v2.1 (Esteira de Qualidade 8 Gates).

Arquitetura: pipeline eliminatório com short-circuit real.
Cada gate pode ELIMINAR, BLOQUEAR, PENALIZAR ou APROVAR.
Eliminado = pipeline para. Nenhum preço bom reverte falha nos Gates 0–3.

Hierarquia obrigatória:
  Gate 0 - Validação dos dados
  Gate 1 - Elegibilidade (liquidez + patrimônio + histórico)
  Gate 2 - Risco estrutural (vacância + concentração)
  Gate 3 - Qualidade da renda (recorrência + sustentabilidade)
  Gate 4 - Preço e margem de segurança
  Gate 5 - Confiabilidade histórica
  Gate 6 - Qualitativo / IA (apenas veta, nunca aprova)
  Gate 7 - Veredito final (síntese + tradução)

Regra de ouro:
  O FIIA não busca o ativo mais barato.
  O FIIA busca o melhor risco-retorno comprável dentro da carteira.
"""

from typing import Optional
from datetime import date

from banco import db
from processamento.confiabilidade import calcular_score as calcular_confiabilidade
from processamento.margem_seguranca import calcular_margem_seguranca
from processamento.dividendo_recorrente import calcular_dy_recorrente, percentual_recorrente
from mercado.comparador_cdi import calcular_premio
from mercado.semaforo_macro import avaliar as avaliar_macro, teto_decisao as teto_macro
from mercado.contexto_setorial import score_segmento
from decisao.dimensionamento import calcular as calcular_dimensionamento
from decisao.zonas_entrada import calcular as calcular_zonas
from config.settings import (
    LIQUIDEZ_MINIMA_DIARIA,
    CONFIABILIDADE_MINIMA,
    HISTORICO_MINIMO_MESES,
    PERCENTUAL_RECORRENTE_MINIMO,
    PREMIO_CDI_MINIMO,
)


# ─────────────────────────────────────────────────────────────────────────────
# Limiares de decisão
# ─────────────────────────────────────────────────────────────────────────────

_LIQUIDEZ_MINIMA_GATE1        = 1_000_000   # R$ 1M/dia - gate 1
_PATRIMONIO_MINIMO            = 100_000_000 # R$ 100M - gate 1
_HISTORICO_MINIMO_MESES_GATE1 = 12          # meses - gate 1

_VACANCIA_LIMITE_ELIMINAR     = 20.0        # % - gate 2
_VACANCIA_LIMITE_PENALIZAR    = 15.0        # % - gate 2
_ATIVOS_MINIMOS_TIJOLO        = 5           # qtd imóveis - gate 2

_RECORRENCIA_MINIMA           = 0.70        # 70% do DY deve ser recorrente - gate 3
_QUEDAS_CONSECUTIVAS_LIMITE   = 3           # meses em queda consecutiva - gate 3

_MARGEM_COMPRAR_FORTE         = 0.30        # >30%  - comprar
_MARGEM_COMPRAR_PARCIAL       = 0.15        # 15-30% - comprar parcial
_MARGEM_AGUARDAR              = 0.05        # 5-15% - aguardar
# < 5% ou negativa - evitar

_SCORE_IA_VETO                = 4           # score IA <= 4 -> veto qualitativo


# ─────────────────────────────────────────────────────────────────────────────
# Helper: resultado de gate padronizado
# ─────────────────────────────────────────────────────────────────────────────

def _gate_result(gate: int, status: str, motivo: str, penalidades: list = None) -> dict:
    return {
        "gate":       gate,
        "status":     status,
        "motivo":     motivo,
        "penalidades": penalidades or [],
        "eliminado":  status.startswith("BLOQUEADO") or status.startswith("ELIMINADO"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
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
        return (date.today() - inicio).days // 30
    except Exception:
        return 0


def _queda_dividendos_consecutivos(ticker: str) -> int:
    rows = db.buscar_todos(
        "SELECT valor FROM dividendos WHERE ticker = ? ORDER BY data_pagamento DESC LIMIT 6",
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


def _quando_revisar(decisao: str, margem: Optional[float], vacancia: Optional[float],
                    tom_gestor: Optional[str]) -> str:
    if decisao == "COMPRAR":
        return "Revisar se preço subir mais de 20% ou no próximo relatório gerencial."
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
    if decisao in ("EVITAR", "ELIMINADO"):
        return "Reavaliar somente se fundamentos melhorarem ou preço recuar significativamente."
    return "Revisar no próximo ciclo semanal do radar."


# ─────────────────────────────────────────────────────────────────────────────
# Gates 0–6
# ─────────────────────────────────────────────────────────────────────────────

def _gate0_validacao(ticker: str, ind: dict, fii_info: dict) -> dict:
    """
    Gate 0 - Validação dos dados.
    Bloqueia se campos essenciais estiverem ausentes.
    Não é rejeição de mérito. É bloqueio técnico: sem dado confiável,
    qualquer decisão é falsa precisão.
    """
    ausentes = []
    for campo in ("preco", "pvp", "liquidez_diaria", "vpa"):
        if ind.get(campo) is None:
            ausentes.append(campo)

    if not fii_info.get("segmento"):
        ausentes.append("segmento")

    tem_dy    = ind.get("dy_12m") is not None
    tem_divs  = db.buscar_um(
        "SELECT COUNT(*) as qtd FROM dividendos WHERE ticker = ?", (ticker,)
    )
    if not tem_dy and (not tem_divs or tem_divs["qtd"] < 1):
        ausentes.append("dy_12m_ou_historico_dividendos")

    if ausentes:
        return _gate_result(
            0, "BLOQUEADO_DADOS_INSUFICIENTES",
            f"Campos essenciais ausentes: {', '.join(ausentes)}."
        )

    # Semáforo macro — não elimina, mas registra teto
    macro = avaliar_macro()
    if macro["cor"] == "VERMELHO":
        return _gate_result(
            0, "APROVADO_DADOS_SEMAFORO_VERMELHO",
            f"Dados OK. Semáforo MACRO: VERMELHO — {macro['motivo']} "
            f"Teto de decisão: {macro['teto_decisao']}."
        )

    return _gate_result(0, "APROVADO_DADOS", f"Dados mínimos presentes. Semáforo macro: {macro['cor']}.")


def _gate1_elegibilidade(ind: dict, fii_info: dict, meses_hist: int) -> dict:
    """
    Gate 1 - Elegibilidade básica.
    Não adianta o fundo parecer bom se o investidor não consegue sair dele.
    """
    liquidez   = ind.get("liquidez_diaria") or 0.0
    patrimonio = ind.get("patrimonio_liquido")

    if liquidez < _LIQUIDEZ_MINIMA_GATE1:
        val = f"R${liquidez:,.0f}" if liquidez else "desconhecida"
        return _gate_result(
            1, "ELIMINADO_LIQUIDEZ",
            f"Liquidez diária ({val}) abaixo de R${_LIQUIDEZ_MINIMA_GATE1:,.0f}. "
            "Risco real de não conseguir sair da posição."
        )

    if patrimonio is not None and patrimonio < _PATRIMONIO_MINIMO:
        return _gate_result(
            1, "ELIMINADO_TAMANHO",
            f"Patrimônio (R${patrimonio:,.0f}) abaixo de R${_PATRIMONIO_MINIMO:,.0f}. "
            "Fundo pequeno demais para liquidez estrutural."
        )

    if meses_hist < _HISTORICO_MINIMO_MESES_GATE1:
        return _gate_result(
            1, "BLOQUEADO_HISTORICO_INSUFICIENTE",
            f"Apenas {meses_hist} meses de histórico (mínimo: {_HISTORICO_MINIMO_MESES_GATE1}). "
            "Impossível avaliar comportamento em ciclos."
        )

    return _gate_result(1, "APROVADO_ELEGIBILIDADE", "Liquidez, tamanho e histórico adequados.")


def _gate2_risco_estrutural(ticker: str, ind: dict, fii_info: dict) -> dict:
    """
    Gate 2 - Risco estrutural.
    Um fundo barato com estrutura ruim é armadilha de valor.
    """
    segmento    = (fii_info.get("segmento") or "").upper()
    tipo        = (fii_info.get("tipo") or "").upper()
    penalidades = []

    if tipo == "DESENVOLVIMENTO":
        return _gate_result(
            2, "ELIMINADO_RISCO_ESTRUTURAL",
            "Fundo de desenvolvimento: risco estruturalmente diferente. "
            "Sem entrada automática - avaliação humana obrigatória."
        )

    eh_papel = "PAPEL" in segmento or "RECEB" in segmento

    if not eh_papel:
        vacancia = ind.get("vacancia_fisica")
        if vacancia is not None:
            if vacancia > _VACANCIA_LIMITE_ELIMINAR:
                return _gate_result(
                    2, "ELIMINADO_RISCO_ESTRUTURAL",
                    f"Vacância física de {vacancia:.1f}% acima do limite de "
                    f"{_VACANCIA_LIMITE_ELIMINAR:.0f}%. Risco de renda comprometida."
                )
            elif vacancia > _VACANCIA_LIMITE_PENALIZAR:
                penalidades.append(
                    f"Vacância elevada ({vacancia:.1f}%) - zona de atenção "
                    f"({_VACANCIA_LIMITE_PENALIZAR:.0f}%–{_VACANCIA_LIMITE_ELIMINAR:.0f}%)."
                )

        qtd_ativos = ind.get("qtd_ativos")
        if qtd_ativos is not None and qtd_ativos < _ATIVOS_MINIMOS_TIJOLO:
            penalidades.append(
                f"Concentração alta: apenas {int(qtd_ativos)} imóveis "
                f"(mínimo recomendado: {_ATIVOS_MINIMOS_TIJOLO})."
            )

    if penalidades:
        return _gate_result(
            2, "PENALIZADO_ESTRUTURA",
            "Estrutura com pontos de atenção - aprovado com penalidades.",
            penalidades=penalidades
        )

    return _gate_result(2, "APROVADO_ESTRUTURA", "Estrutura dentro dos parâmetros aceitáveis.")


def _gate3_qualidade_renda(ticker: str, ind: dict, pct_rec: Optional[float],
                            dy_recorrente: Optional[float], premio_cdi: Optional[float],
                            quedas: int) -> dict:
    """
    Gate 3 - Qualidade da renda.
    Este gate antecede o preço. Não importa quão barato esteja o fundo:
    se a renda não é recorrente e sustentável, ele é eliminado aqui.
    DY alto por evento único não é renda - é ilusão.
    """
    penalidades = []

    if pct_rec is None:
        return _gate_result(
            3, "ELIMINADO_RENDA_INSUFICIENTE",
            "Histórico insuficiente para avaliar recorrência dos dividendos. "
            "Impossível distinguir renda real de distribuição pontual."
        )

    if pct_rec < _RECORRENCIA_MINIMA:
        return _gate_result(
            3, "ELIMINADO_RENDA_INSUFICIENTE",
            f"Apenas {pct_rec*100:.0f}% do dividendo é recorrente "
            f"(mínimo: {_RECORRENCIA_MINIMA*100:.0f}%). "
            "DY pode estar inflado por distribuições extraordinárias não sustentáveis."
        )

    if dy_recorrente is not None and premio_cdi is not None and premio_cdi < 0:
        return _gate_result(
            3, "ELIMINADO_RENDA_INSUFICIENTE",
            f"DY recorrente abaixo do CDI (prêmio: {premio_cdi:.2f} pp). "
            "Renda fixa remunera melhor sem o risco deste ativo."
        )

    if quedas >= _QUEDAS_CONSECUTIVAS_LIMITE:
        return _gate_result(
            3, "ELIMINADO_RENDA_INSUFICIENTE",
            f"Dividendos em queda por {quedas} meses consecutivos. "
            "Sinal forte de deterioração da renda."
        )

    if pct_rec < 0.85:
        penalidades.append(
            f"Recorrência moderada ({pct_rec*100:.0f}%) - acompanhar próximos pagamentos."
        )

    if penalidades:
        return _gate_result(
            3, "PENALIZADO_DY_IRREGULAR",
            "Renda aprovada mas com irregularidades menores.",
            penalidades=penalidades
        )

    return _gate_result(3, "APROVADO_RENDA", "Dividendos recorrentes e sustentáveis.")


def _gate4_preco(margem: Optional[float], margem_stress: Optional[float],
                 pvp: Optional[float], segmento: str) -> dict:
    """
    Gate 4 - Preço e margem de segurança.
    Qualidade sem preço bom vira aguardar.
    Preço bom sem qualidade já foi eliminado antes.
    Este gate classifica - não elimina definitivamente.
    """
    if margem is None:
        return _gate_result(4, "BLOQUEADO_PRECO",
                            "Não foi possível calcular margem de segurança.")

    penalidades = []

    eh_papel = "PAPEL" in (segmento or "").upper() or "RECEB" in (segmento or "").upper()
    if pvp is not None and not eh_papel and pvp > 1.10:
        penalidades.append(f"P/VP elevado ({pvp:.2f}) para fundo de tijolo.")

    if margem < 0:
        return _gate_result(
            4, "EVITAR_PRECO",
            f"Margem negativa ({margem*100:.1f}%). Preço acima do valor justo estimado.",
            penalidades=penalidades
        )

    if margem < _MARGEM_AGUARDAR:
        return _gate_result(
            4, "AGUARDAR_PRECO",
            f"Margem insuficiente ({margem*100:.1f}%). "
            "Fundo pode ser saudável, mas preço não oferece desconto para entrada.",
            penalidades=penalidades
        )

    if margem < _MARGEM_COMPRAR_PARCIAL:
        return _gate_result(
            4, "MARGEM_MODERADA",
            f"Margem positiva ({margem*100:.1f}%), adequada para entrada parcial.",
            penalidades=penalidades
        )

    # margem >= 15%
    if margem_stress is not None and margem_stress < 0:
        penalidades.append(
            f"Margem de stress negativa ({margem_stress*100:.1f}%): "
            "desconto real mas frágil em cenário adverso."
        )

    return _gate_result(
        4, "MARGEM_FORTE",
        f"Margem expressiva ({margem*100:.1f}%). Candidato forte.",
        penalidades=penalidades
    )


def _gate5_confiabilidade(confiabilidade: int) -> dict:
    """
    Gate 5 - Confiabilidade histórica.
    Não elimina por mérito - bloqueia quando o dado é fraco demais para confiar.
    Dois fundos com o mesmo resultado mas dados diferentes não têm o mesmo peso.
    """
    if confiabilidade < 60:
        return _gate_result(
            5, "BLOQUEADO_CONFIABILIDADE_BAIXA",
            f"Confiabilidade dos dados em {confiabilidade}% (mínimo: 60%). "
            "Decidir com dado fraco demais é falsa precisão."
        )
    if confiabilidade < 70:
        nivel = "CONFIANCA_BAIXA"
    elif confiabilidade < 85:
        nivel = "CONFIANCA_MEDIA"
    else:
        nivel = "CONFIANCA_ALTA"

    return _gate_result(
        5, nivel,
        f"Confiabilidade dos dados: {confiabilidade}%."
    )


def _gate6_qualitativo(score_ia: Optional[float], riscos_ia: Optional[list],
                        tom_gestor: Optional[str], ia_status: str) -> dict:
    """
    Gate 6 - Qualitativo / IA.
    A IA não aprova compra. A IA só veta, reduz confiança ou complementa.
    Se os números passaram, a IA verifica o que os números ainda não capturaram.
    """
    if ia_status != "OK" or score_ia is None:
        return _gate_result(
            6, "IA_INDISPONIVEL",
            "Análise qualitativa indisponível. Decisão baseada apenas nos indicadores quantitativos."
        )

    if score_ia <= _SCORE_IA_VETO:
        riscos_str = "; ".join(riscos_ia) if riscos_ia else "não detalhados"
        return _gate_result(
            6, "VETO_QUALITATIVO",
            f"IA identificou riscos graves (score qualitativo: {score_ia}/10). "
            f"Riscos: {riscos_str}."
        )

    penalidades = []
    if tom_gestor == "defensivo":
        penalidades.append("Tom defensivo do gestor no último relatório gerencial.")
    if score_ia <= 6:
        penalidades.append(f"Score qualitativo moderado ({score_ia}/10).")

    if penalidades:
        return _gate_result(
            6, "RISCO_QUALITATIVO_ALTO",
            "Análise qualitativa aprovada com ressalvas.",
            penalidades=penalidades
        )

    return _gate_result(
        6, "QUALITATIVO_OK",
        f"Análise qualitativa sem red flags. Score IA: {score_ia}/10."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Gate 7 - Veredito final
# ─────────────────────────────────────────────────────────────────────────────

def _gate7_veredito(gates: dict, margem: Optional[float], confiabilidade: int,
                     tom_gestor: Optional[str], ia_status: str, segmento: str = "") -> tuple:
    """Traduz os resultados dos gates em (decisao, motivo) aplicando teto macro."""
    g4 = gates.get(4, {})
    g5 = gates.get(5, {})
    g6 = gates.get(6, {})

    g4_status = g4.get("status", "")
    g6_status = g6.get("status", "")

    # Veto qualitativo
    if g6_status == "VETO_QUALITATIVO":
        if g4_status == "MARGEM_FORTE":
            return "MONITORAR", g6.get("motivo", "Veto qualitativo.")
        return "EVITAR", g6.get("motivo", "Veto qualitativo.")

    # Decisão base pelo Gate 4
    if g4_status == "EVITAR_PRECO":
        decisao, motivo = "EVITAR", g4.get("motivo", "Margem negativa.")
    elif g4_status == "AGUARDAR_PRECO":
        decisao, motivo = "AGUARDAR", g4.get("motivo", "Margem insuficiente.")
    elif g4_status == "BLOQUEADO_PRECO":
        decisao, motivo = "MONITORAR", g4.get("motivo", "Preço não calculável.")
    elif g4_status == "MARGEM_MODERADA":
        decisao, motivo = "COMPRAR_PARCIAL", g4.get("motivo", "Margem moderada.")
    elif g4_status == "MARGEM_FORTE":
        decisao, motivo = "COMPRAR", g4.get("motivo", "Margem expressiva.")
    else:
        decisao, motivo = "MONITORAR", "Status de preço indefinido."

    # Confiabilidade baixa degrada compra
    if g5.get("status") == "CONFIANCA_BAIXA" and decisao in ("COMPRAR", "COMPRAR_PARCIAL"):
        decisao = "MONITORAR"
        motivo = f"{motivo} Confiabilidade baixa ({confiabilidade}%) - não suficiente para entrada."

    # Tom defensivo rebaixa compra forte para parcial
    if (tom_gestor == "defensivo" and g6_status == "RISCO_QUALITATIVO_ALTO"
            and decisao == "COMPRAR"):
        decisao = "COMPRAR_PARCIAL"
        motivo = f"{motivo} Tom defensivo do gestor - entrada parcial mais prudente."

    # IA indisponível: anota mas não bloqueia
    if ia_status != "OK" and decisao in ("COMPRAR", "COMPRAR_PARCIAL"):
        motivo = f"{motivo} (sem validação qualitativa - IA indisponível)."

    # Aplica teto macro
    teto = teto_macro()
    ordem = ["COMPRAR", "COMPRAR_PARCIAL", "AGUARDAR", "MONITORAR", "EVITAR"]
    if decisao in ordem and teto in ordem:
        if ordem.index(decisao) < ordem.index(teto):
            motivo = f"{motivo} [Teto macro: {teto}]"
            decisao = teto

    return decisao, motivo


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
    Pipeline eliminatório de 8 gates.
    Se qualquer gate 0–3 falha, o pipeline para e retorna o status do gate.
    Nenhuma margem de preço reverte uma falha nos gates de qualidade.
    """
    ticker = ticker.upper().strip()

    ind_row      = db.buscar_um(
        "SELECT * FROM indicadores WHERE ticker = ? ORDER BY data DESC LIMIT 1",
        (ticker,)
    )
    fii_info_row = db.buscar_um("SELECT * FROM fiis WHERE ticker = ?", (ticker,))

    ind      = dict(ind_row)      if ind_row      else {}
    fii_info = dict(fii_info_row) if fii_info_row else {}

    if not ind_row or not fii_info_row:
        return _montar_retorno(
            ticker, "BLOQUEADO_DADOS_INSUFICIENTES",
            "Fundo não encontrado no banco de dados.",
            gate_parada=0, gates={}, penalidades=[], alertas=[],
            confiabilidade=0, preco=None, pvp=None, dy_12m=None,
            margem=None, margem_stress=None, preco_justo=None,
            preco_entrada=None, preco_stress_val=None, dy_recorrente=None,
            pct_rec=None, premio_cdi=None, vacancia=None, liquidez=None,
            segmento="INDEFINIDO", meses_hist=0, score_ia=score_ia,
            riscos_ia=riscos_ia, tom_gestor=tom_gestor, ia_status=ia_status
        )

    # Cálculos derivados compartilhados entre gates
    preco         = ind.get("preco")
    pvp           = ind.get("pvp")
    dy_12m        = ind.get("dy_12m")
    liquidez      = ind.get("liquidez_diaria")
    vacancia      = ind.get("vacancia_fisica")
    segmento      = fii_info.get("segmento", "INDEFINIDO")

    confiabilidade  = calcular_confiabilidade(ticker)
    margem          = calcular_margem_seguranca(ticker)
    margem_stress   = calcular_margem_seguranca(ticker, cenario_stress=True)
    dy_recorrente   = calcular_dy_recorrente(ticker, preco) if preco else None
    pct_rec         = percentual_recorrente(ticker)
    premio_cdi      = calcular_premio(dy_recorrente)
    meses_hist      = _meses_historico(ticker)
    quedas_consec   = _queda_dividendos_consecutivos(ticker)

    preco_justo      = preco * (1 + margem)        if preco and margem is not None else None
    preco_entrada    = preco_justo * 0.95           if preco_justo else None
    preco_stress_val = preco * (1 + margem_stress)  if preco and margem_stress is not None else None

    gates      = {}
    alertas    = []
    penalidades_acumuladas = []

    def _check(g):
        """Registra gate e retorna True se eliminou."""
        gates[g["gate"]] = g
        penalidades_acumuladas.extend(g["penalidades"])
        return g["eliminado"]

    def _saida(g):
        return _montar_retorno(
            ticker, g["status"], g["motivo"],
            gate_parada=g["gate"], gates=gates,
            penalidades=penalidades_acumuladas, alertas=alertas,
            confiabilidade=confiabilidade, preco=preco, pvp=pvp,
            dy_12m=dy_12m, margem=margem, margem_stress=margem_stress,
            preco_justo=preco_justo, preco_entrada=preco_entrada,
            preco_stress_val=preco_stress_val, dy_recorrente=dy_recorrente,
            pct_rec=pct_rec, premio_cdi=premio_cdi, vacancia=vacancia,
            liquidez=liquidez, segmento=segmento, meses_hist=meses_hist,
            score_ia=score_ia, riscos_ia=riscos_ia, tom_gestor=tom_gestor,
            ia_status=ia_status
        )

    # ── Gate 0: Validação ────────────────────────────────────────────────
    g0 = _gate0_validacao(ticker, ind, fii_info)
    if _check(g0): return _saida(g0)

    # ── Gate 1: Elegibilidade ────────────────────────────────────────────
    g1 = _gate1_elegibilidade(ind, fii_info, meses_hist)
    if _check(g1): return _saida(g1)

    # ── Gate 2: Risco estrutural ─────────────────────────────────────────
    g2 = _gate2_risco_estrutural(ticker, ind, fii_info)
    if _check(g2): return _saida(g2)

    # ── Gate 3: Qualidade da renda ───────────────────────────────────────
    # INVERSÃO CENTRAL: este gate antecede o preço.
    # 50% de margem não salva dividendo não recorrente.
    g3 = _gate3_qualidade_renda(ticker, ind, pct_rec, dy_recorrente, premio_cdi, quedas_consec)
    if _check(g3): return _saida(g3)

    # ── Gate 4: Preço e margem ───────────────────────────────────────────
    g4 = _gate4_preco(margem, margem_stress, pvp, segmento)
    _check(g4)  # não elimina - apenas classifica

    # ── Gate 5: Confiabilidade ───────────────────────────────────────────
    g5 = _gate5_confiabilidade(confiabilidade)
    if _check(g5): return _saida(g5)

    # ── Gate 6: Qualitativo / IA ─────────────────────────────────────────
    g6 = _gate6_qualitativo(score_ia, riscos_ia, tom_gestor, ia_status)
    if g6["status"] == "VETO_QUALITATIVO":
        alertas.append(g6["motivo"])
    _check(g6)

    # ── Gate 7: Veredito final ───────────────────────────────────────────
    decisao, motivo = _gate7_veredito(gates, margem, confiabilidade, tom_gestor, ia_status)

    if confiabilidade >= 90 and ia_status == "OK":
        confianca = "ALTA"
    elif confiabilidade >= 75 or ia_status == "OK":
        confianca = "MEDIA"
    else:
        confianca = "BAIXA"

    revisao = _quando_revisar(decisao, margem, vacancia, tom_gestor)

    resultado = _montar_retorno(
        ticker, decisao, motivo,
        gate_parada=7, gates=gates,
        penalidades=penalidades_acumuladas, alertas=alertas,
        confiabilidade=confiabilidade, preco=preco, pvp=pvp,
        dy_12m=dy_12m, margem=margem, margem_stress=margem_stress,
        preco_justo=preco_justo, preco_entrada=preco_entrada,
        preco_stress_val=preco_stress_val, dy_recorrente=dy_recorrente,
        pct_rec=pct_rec, premio_cdi=premio_cdi, vacancia=vacancia,
        liquidez=liquidez, segmento=segmento, meses_hist=meses_hist,
        score_ia=score_ia, riscos_ia=riscos_ia, tom_gestor=tom_gestor,
        ia_status=ia_status, confianca=confianca, revisao=revisao
    )

    # Dimensionamento e zonas — só para decisões de compra
    if decisao in ("COMPRAR", "COMPRAR_PARCIAL", "AGUARDAR", "MONITORAR"):
        try:
            resultado["dimensionamento"] = calcular_dimensionamento(
                ticker=ticker,
                margem=margem,
                meses_historico=meses_hist,
                travas_ativas=[g["status"] for g in gates.values() if "ELIMINADO" in g["status"] or "BLOQUEADO" in g["status"]],
                segmento=segmento,
                score_ia=score_ia,
            )
        except Exception:
            pass

        try:
            resultado["zonas_entrada"] = calcular_zonas(ticker)
        except Exception:
            pass

    return resultado


# ─────────────────────────────────────────────────────────────────────────────
# Montador de retorno padronizado
# ─────────────────────────────────────────────────────────────────────────────

def _montar_retorno(
    ticker, decisao, motivo, gate_parada, gates,
    penalidades, alertas, confiabilidade,
    preco, pvp, dy_12m, margem, margem_stress,
    preco_justo, preco_entrada, preco_stress_val,
    dy_recorrente, pct_rec, premio_cdi, vacancia,
    liquidez, segmento, meses_hist, score_ia,
    riscos_ia, tom_gestor, ia_status,
    confianca: str = None, revisao: str = None,
) -> dict:
    if confianca is None:
        confianca = "ALTA" if confiabilidade >= 85 else "MEDIA" if confiabilidade >= 70 else "BAIXA"

    if revisao is None:
        revisao = _quando_revisar(decisao, margem, vacancia, tom_gestor)

    trilha = [
        f"Gate {n}: {g['status']}"
        for n, g in sorted(gates.items())
    ]

    return {
        # Decisão
        "ticker":          ticker,
        "decisao":         decisao,
        "motivo":          motivo,
        "gate_parada":     gate_parada,
        "trilha_gates":    trilha,
        "confianca":       confianca,

        # Preços
        "preco_atual":     preco,
        "preco_justo":     round(preco_justo, 2)      if preco_justo      else None,
        "preco_entrada":   round(preco_entrada, 2)    if preco_entrada    else None,
        "preco_stress":    round(preco_stress_val, 2) if preco_stress_val else None,

        # Indicadores
        "margem":              round(margem * 100, 1)         if margem is not None      else None,
        "margem_stress":       round(margem_stress * 100, 1)  if margem_stress is not None else None,
        "pvp":                 pvp,
        "dy_12m_pct":          round(dy_12m * 100, 2)         if dy_12m                  else None,
        "dy_recorrente_pct":   round(dy_recorrente * 100, 2)  if dy_recorrente           else None,
        "pct_recorrente":      round(pct_rec * 100, 1)        if pct_rec is not None     else None,
        "premio_cdi":          round(premio_cdi, 2)           if premio_cdi is not None  else None,
        "vacancia":            vacancia,
        "liquidez":            liquidez,
        "segmento":            segmento,
        "meses_historico":     meses_hist,

        # Qualidade e alertas
        "confiabilidade":      confiabilidade,
        "penalidades":         penalidades,
        "alertas":             alertas,

        # IA
        "score_ia":            score_ia,
        "riscos_ia":           riscos_ia or [],
        "tom_gestor":          tom_gestor or "nao_disponivel",
        "ia_status":           ia_status,

        # Gates detalhados (debug + UI)
        "gates_detalhes": {
            str(n): {"status": g["status"], "motivo": g["motivo"]}
            for n, g in sorted(gates.items())
        },

        # Dimensionamento e zonas de entrada
        "dimensionamento": None,  # calculado abaixo se aplicável
        "zonas_entrada":   None,

        # Metadados
        "revisao":         revisao,
        "data_analise":    date.today().isoformat(),
        "versao_modelo":   "2.1",
    }
