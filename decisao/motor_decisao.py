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

def _gate_result(gate: int, status: str, motivo: str, penalidades: list = None,
                 metricas: dict = None, fontes: list = None, motivos: list = None) -> dict:
    eliminado = status.startswith("BLOQUEADO") or status.startswith("ELIMINADO")
    aprovado = not (
        status.startswith("BLOQUEADO")
        or status.startswith("ELIMINADO")
        or status.startswith("VETO")
    )
    lista_motivos = motivos or [motivo]

    return {
        "gate":       gate,
        "status":     status,
        "aprovado":   aprovado,
        "eliminado":  eliminado,
        "motivo":     motivo,
        "motivos":    lista_motivos,
        "metricas":   metricas or {},
        "fontes":     fontes or [],
        "penalidades": penalidades or [],
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

def _gate0_validacao(ticker: str, ind: dict, fii_info: dict, contexto: dict | None = None) -> dict:
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
    if contexto:
        tem_divs_qtd = 1 if contexto.get("recorrencia_dividendos_pct") is not None else 0
    else:
        tem_divs  = db.buscar_um(
            "SELECT COUNT(*) as qtd FROM dividendos WHERE ticker = ?", (ticker,)
        )
        tem_divs_qtd = tem_divs["qtd"] if tem_divs else 0

    if not tem_dy and tem_divs_qtd < 1:
        ausentes.append("dy_12m_ou_historico_dividendos")

    if ausentes:
        return _gate_result(
            0, "BLOQUEADO_DADOS_INSUFICIENTES",
            f"Campos essenciais ausentes: {', '.join(ausentes)}.",
            metricas={"campos_ausentes": ausentes}, fontes=["contexto", "banco"]
        )

    # Semáforo macro — não elimina, mas registra teto
    if contexto:
        macro = contexto.get("semaforo_macro") or {}
    else:
        macro = avaliar_macro()

    if macro.get("cor") == "VERMELHO":
        return _gate_result(
            0, "APROVADO_DADOS_SEMAFORO_VERMELHO",
            f"Dados OK. Semáforo MACRO: VERMELHO — {macro.get('motivo')} "
            f"Teto de decisão: {macro.get('teto_decisao')}.",
            metricas={"semaforo": macro.get("cor"), "teto_macro": macro.get("teto_decisao")},
            fontes=["BCB", "B3"]
        )

    return _gate_result(0, "APROVADO_DADOS", f"Dados mínimos presentes. Semáforo macro: {macro.get('cor')}.",
                        metricas={"semaforo": macro.get("cor")}, fontes=["contexto"])



def _gate1_elegibilidade(ind: dict, fii_info: dict, meses_hist: int) -> dict:
    """
    Gate 1 - Elegibilidade básica.
    Não adianta o fundo parecer bom se o investidor não consegue sair dele.
    """
    liquidez   = ind.get("liquidez_diaria") or 0.0
    patrimonio = ind.get("patrimonio_liquido")

    metrics = {"liquidez": liquidez, "patrimonio": patrimonio, "meses_hist": meses_hist}

    if liquidez < _LIQUIDEZ_MINIMA_GATE1:
        val = f"R${liquidez:,.0f}" if liquidez else "desconhecida"
        return _gate_result(
            1, "ELIMINADO_LIQUIDEZ",
            f"Liquidez diária ({val}) abaixo de R${_LIQUIDEZ_MINIMA_GATE1:,.0f}. "
            "Risco real de não conseguir sair da posição.",
            metricas=metrics
        )

    if patrimonio is not None and patrimonio < _PATRIMONIO_MINIMO:
        return _gate_result(
            1, "ELIMINADO_TAMANHO",
            f"Patrimônio (R${patrimonio:,.0f}) abaixo de R${_PATRIMONIO_MINIMO:,.0f}. "
            "Fundo pequeno demais para liquidez estrutural.",
            metricas=metrics
        )

    if meses_hist < _HISTORICO_MINIMO_MESES_GATE1:
        return _gate_result(
            1, "BLOQUEADO_HISTORICO_INSUFICIENTE",
            f"Apenas {meses_hist} meses de histórico (mínimo: {_HISTORICO_MINIMO_MESES_GATE1}). "
            "Impossível avaliar comportamento em ciclos.",
            metricas=metrics
        )

    return _gate_result(1, "APROVADO_ELEGIBILIDADE", "Liquidez, tamanho e histórico adequados.", metricas=metrics)


def _gate2_risco_estrutural(ticker: str, ind: dict, fii_info: dict) -> dict:
    """
    Gate 2 - Risco estrutural.
    Um fundo barato com estrutura ruim é armadilha de valor.
    """
    segmento    = (fii_info.get("segmento") or "").upper()
    tipo        = (fii_info.get("tipo") or "").upper()
    penalidades = []

    eh_papel = "PAPEL" in (segmento or "").upper() or "RECEB" in (segmento or "").upper()
    metrics = {"segmento": segmento, "tipo": tipo, "eh_papel": eh_papel}

    if tipo == "DESENVOLVIMENTO":
        return _gate_result(
            2, "ELIMINADO_RISCO_ESTRUTURAL",
            "Fundo de desenvolvimento: risco estruturalmente diferente. "
            "Sem entrada automática - avaliação humana obrigatória.",
            metricas=metrics
        )

    if not eh_papel:
        vacancia = ind.get("vacancia_fisica")
        metrics["vacancia_fisica"] = vacancia
        if vacancia is not None:
            if vacancia > _VACANCIA_LIMITE_ELIMINAR:
                return _gate_result(
                    2, "ELIMINADO_RISCO_ESTRUTURAL",
                    f"Vacância física de {vacancia:.1f}% acima do limite de "
                    f"{_VACANCIA_LIMITE_ELIMINAR:.0f}%. Risco de renda comprometida.",
                    metricas=metrics
                )
            elif vacancia > _VACANCIA_LIMITE_PENALIZAR:
                penalidades.append(
                    f"Vacância elevada ({vacancia:.1f}%) - zona de atenção "
                    f"({_VACANCIA_LIMITE_PENALIZAR:.0f}%–{_VACANCIA_LIMITE_ELIMINAR:.0f}%)."
                )

        qtd_ativos = ind.get("qtd_ativos")
        metrics["qtd_ativos"] = qtd_ativos
        if qtd_ativos is not None and qtd_ativos < _ATIVOS_MINIMOS_TIJOLO:
            penalidades.append(
                f"Concentração alta: apenas {int(qtd_ativos)} imóveis "
                f"(mínimo recomendado: {_ATIVOS_MINIMOS_TIJOLO})."
            )

    if penalidades:
        return _gate_result(
            2, "PENALIZADO_ESTRUTURA",
            "Estrutura com pontos de atenção - aprovado com penalidades.",
            penalidades=penalidades, metricas=metrics
        )

    return _gate_result(2, "APROVADO_ESTRUTURA", "Estrutura dentro dos parâmetros aceitáveis.", metricas=metrics)


def _gate3_qualidade_renda(ticker: str, ind: dict, pct_rec: Optional[float],
                            dy_recorrente: Optional[float], premio_cdi: Optional[float],
                            quedas: int, segmento: str = "") -> dict:
    """
    Gate 3 - Qualidade da renda.
    Este gate antecede o preço. Não importa quão barato esteja o fundo:
    se a renda não é recorrente e sustentável, ele é eliminado aqui.
    DY alto por evento único não é renda - é ilusão.
    """
    penalidades = []
    metrics = {
        "pct_recorrente": pct_rec,
        "dy_recorrente": dy_recorrente,
        "premio_cdi": premio_cdi,
        "quedas_consecutivas": quedas,
        "segmento": segmento
    }

    segmento_norm = (segmento or "").upper()
    eh_papel = "PAPEL" in segmento_norm or "RECEB" in segmento_norm

    if pct_rec is None:
        return _gate_result(
            3, "ELIMINADO_RENDA_INSUFICIENTE",
            "Histórico insuficiente para avaliar recorrência dos dividendos. "
            "Impossível distinguir renda real de distribuição pontual.",
            metricas=metrics
        )

    if pct_rec < _RECORRENCIA_MINIMA:
        return _gate_result(
            3, "ELIMINADO_RENDA_INSUFICIENTE",
            f"Apenas {pct_rec*100:.0f}% do dividendo é recorrente "
            f"(mínimo: {_RECORRENCIA_MINIMA*100:.0f}%). "
            "DY pode estar inflado por distribuições extraordinárias não sustentáveis.",
            metricas=metrics
        )

    if dy_recorrente is not None and premio_cdi is not None and premio_cdi < 0:
        if eh_papel:
            return _gate_result(
                3, "ELIMINADO_RENDA_INSUFICIENTE",
                f"DY recorrente abaixo do CDI (prêmio: {premio_cdi:.2f} pp). "
                "Para FII de papel/recebíveis, a renda precisa competir diretamente com o CDI.",
                metricas=metrics
            )
        penalidades.append(
            f"DY recorrente abaixo do CDI (prêmio: {premio_cdi:.2f} pp). "
            "Para FII de tijolo/renda urbana/logística, seguir para avaliação de preço, contratos e margem."
        )

    if quedas >= _QUEDAS_CONSECUTIVAS_LIMITE:
        return _gate_result(
            3, "ELIMINADO_RENDA_INSUFICIENTE",
            f"Dividendos em queda por {quedas} meses consecutivos. "
            "Sinal forte de deterioração da renda.",
            metricas=metrics
        )

    if pct_rec < 0.85:
        penalidades.append(
            f"Recorrência moderada ({pct_rec*100:.0f}%) - acompanhar próximos pagamentos."
        )

    if penalidades:
        return _gate_result(
            3, "PENALIZADO_DY_IRREGULAR",
            "Renda aprovada mas com irregularidades menores.",
            penalidades=penalidades, metricas=metrics
        )

    return _gate_result(3, "APROVADO_RENDA", "Dividendos recorrentes e sustentáveis.", metricas=metrics)


def _gate4_preco(margem: Optional[float], margem_stress: Optional[float],
                 pvp: Optional[float], segmento: str) -> dict:
    """
    Gate 4 - Preço e margem de segurança.
    Qualidade sem preço bom vira aguardar.
    Preço bom sem qualidade já foi eliminado antes.
    Este gate classifica - não elimina definitivamente.
    """
    metrics = {"margem": margem, "margem_stress": margem_stress, "pvp": pvp}

    if margem is None:
        return _gate_result(4, "BLOQUEADO_PRECO",
                            "Não foi possível calcular margem de segurança.", metricas=metrics)

    penalidades = []

    eh_papel = "PAPEL" in (segmento or "").upper() or "RECEB" in (segmento or "").upper()
    if pvp is not None and not eh_papel and pvp > 1.10:
        penalidades.append(f"P/VP elevado ({pvp:.2f}) para fundo de tijolo.")

    if margem < -0.20:
        return _gate_result(
            4, "EVITAR_PRECO",
            f"Margem muito negativa ({margem*100:.1f}%). Preço muito acima do valor justo estimado.",
            penalidades=penalidades, metricas=metrics
        )

    if margem < -0.05:
        return _gate_result(
            4, "AGUARDAR_PRECO",
            f"Margem negativa moderada ({margem*100:.1f}%). Fundo pode ser bom, mas ainda exige queda para entrada.",
            penalidades=penalidades, metricas=metrics
        )

    if margem < 0:
        return _gate_result(
            4, "MONITORAR_QUALIDADE",
            f"Preço levemente acima do valor justo ({margem*100:.1f}%). Manter no radar pela qualidade estrutural.",
            penalidades=penalidades, metricas=metrics
        )

    if margem < 0.05:
        return _gate_result(
            4, "MONITORAR_ENTRADA",
            f"Margem positiva pequena ({margem*100:.1f}%). Próximo da zona de entrada, mas ainda sem folga relevante.",
            penalidades=penalidades, metricas=metrics
        )

    if margem < _MARGEM_AGUARDAR:
        return _gate_result(
            4, "MARGEM_MODERADA",
            f"Margem positiva ({margem*100:.1f}%), adequada para entrada parcial.",
            penalidades=penalidades, metricas=metrics
        )

    if margem < _MARGEM_COMPRAR_PARCIAL:
        return _gate_result(
            4, "MARGEM_MODERADA",
            f"Margem positiva ({margem*100:.1f}%), adequada para entrada parcial.",
            penalidades=penalidades, metricas=metrics
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
        penalidades=penalidades, metricas=metrics
    )


def _gate5_confiabilidade(confiabilidade: int) -> dict:
    """
    Gate 5 - Confiabilidade histórica.
    Não elimina por mérito - bloqueia quando o dado é fraco demais para confiar.
    Dois fundos com o mesmo resultado mas dados diferentes não têm o mesmo peso.
    """
    metrics = {"score_confianca": confiabilidade}
    if confiabilidade < 60:
        return _gate_result(
            5, "BLOQUEADO_CONFIABILIDADE_BAIXA",
            f"Confiabilidade dos dados em {confiabilidade}% (mínimo: 60%). "
            "Decidir com dado fraco demais é falsa precisão.",
            metricas=metrics
        )
    if confiabilidade < 70:
        nivel = "CONFIANCA_BAIXA"
    elif confiabilidade < 85:
        nivel = "CONFIANCA_MEDIA"
    else:
        nivel = "CONFIANCA_ALTA"

    return _gate_result(
        5, nivel,
        f"Confiabilidade dos dados: {confiabilidade}%.",
        metricas=metrics
    )


def _gate6_qualitativo(score_ia: Optional[float], riscos_ia: Optional[list],
                        tom_gestor: Optional[str], ia_status: str) -> dict:
    """
    Gate 6 - Qualitativo / IA.
    A IA não aprova compra. A IA só veta, reduz confiança ou complementa.
    Se os números passaram, a IA verifica o que os números ainda não capturaram.
    """
    metrics = {"score_ia": score_ia, "tom_gestor": tom_gestor, "ia_status": ia_status}

    if ia_status != "OK" or score_ia is None:
        return _gate_result(
            6, "IA_INDISPONIVEL",
            "Análise qualitativa indisponível. Decisão baseada apenas nos indicadores quantitativos.",
            metricas=metrics
        )

    if score_ia <= _SCORE_IA_VETO:
        riscos_str = "; ".join(riscos_ia) if riscos_ia else "não detalhados"
        return _gate_result(
            6, "VETO_QUALITATIVO",
            f"IA identificou riscos graves (score qualitativo: {score_ia}/10). "
            f"Riscos: {riscos_str}.",
            metricas=metrics, motivos=riscos_ia
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
            penalidades=penalidades, metricas=metrics
        )

    return _gate_result(
        6, "QUALITATIVO_OK",
        f"Análise qualitativa sem red flags. Score IA: {score_ia}/10.",
        metricas=metrics
    )


# ─────────────────────────────────────────────────────────────────────────────
# Gate 7 - Veredito final
# ─────────────────────────────────────────────────────────────────────────────

def _gate7_veredito(gates: dict, margem: Optional[float], confiabilidade: int,
                     tom_gestor: Optional[str], ia_status: str, segmento: str = "", contexto: dict | None = None) -> tuple:
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
    if contexto:
        teto = contexto.get("teto_macro")
    else:
        teto = teto_macro()
    ordem = ["COMPRAR", "COMPRAR_PARCIAL", "AGUARDAR", "MONITORAR", "EVITAR"]
    if decisao in ordem and teto in ordem:
        if ordem.index(decisao) < ordem.index(teto):
            motivo = f"{motivo} [Teto macro: {teto}]"
            decisao = teto

    return decisao, motivo



def _carregar_base_decisao(ticker: str, contexto: dict | None = None) -> tuple[dict, dict]:
    """
    Carrega os dados base (indicadores e fiis) do ativo.
    Se o contexto estiver presente em memória, usa os dados pré-resolvidos.
    Caso contrário (modo legado), realiza as consultas necessárias no SQLite (Achado 4).
    """
    if contexto:
        ind = {
            "preco": contexto.get("preco"),
            "pvp": contexto.get("pvp"),
            "liquidez_diaria": contexto.get("liquidez_diaria"),
            "dy_12m": contexto.get("dy_12m"),
            "vacancia_fisica": contexto.get("vacancia_fisica"),
            "patrimonio_liquido": contexto.get("patrimonio_liquido"),
            "vpa": contexto.get("vpa"),
            "qtd_ativos": contexto.get("qtd_ativos"),
            "confiabilidade": contexto.get("score_confianca"),
        }
        fii_info = {
            "ticker": ticker,
            "nome": contexto.get("nome_fundo") or ticker,
            "segmento": contexto.get("segmento") or "INDEFINIDO",
            "tipo": contexto.get("tipo") or "INDEFINIDO",
        }
        return ind, fii_info

    ind_row = db.buscar_um(
        "SELECT * FROM indicadores WHERE ticker = ? ORDER BY data DESC LIMIT 1",
        (ticker,)
    )
    fii_info_row = db.buscar_um("SELECT * FROM fiis WHERE ticker = ?", (ticker,))

    ind = dict(ind_row) if ind_row else {}
    fii_info = dict(fii_info_row) if fii_info_row else {}
    return ind, fii_info


# ─────────────────────────────────────────────────────────────────────────────
# Interface pública
# ─────────────────────────────────────────────────────────────────────────────

def validar_contexto_completo(contexto: dict) -> list[str]:
    campos_obrigatorios = [
        "ticker", "preco", "vpa", "pvp", "patrimonio_liquido", "liquidez_diaria",
        "dy_12m", "dy_recorrente", "recorrencia_dividendos_pct", "meses_historico",
        "quedas_consecutivas", "score_confianca", "cdi_atual", "selic_atual",
        "ipca_atual", "semaforo_macro", "teto_macro", "premio_cdi", "patrimonio_fonte",
        "nivel_uso_dados", "permitir_decisao", "segmento"
    ]
    ausentes = []
    for c in campos_obrigatorios:
        if c not in contexto or contexto[c] is None:
            ausentes.append(c)
    return ausentes


def decidir(
    ticker: str,
    score_ia: Optional[float] = None,
    riscos_ia: Optional[list] = None,
    tom_gestor: Optional[str] = None,
    ia_status: str = "INDISPONIVEL",
    contexto: Optional[dict] = None,
) -> dict:
    """
    Pipeline eliminatório de 8 gates.
    Se qualquer gate 0–3 falha, o pipeline para e retorna o status do gate.
    Nenhuma margem de preço reverte uma falha nos gates de qualidade.
    """
    ticker = ticker.upper().strip()

    if contexto:
        ausentes = validar_contexto_completo(contexto)
        if ausentes:
            return _montar_retorno(
                ticker, "BLOQUEADO_CONTEXTO_INCOMPLETO",
                f"Contexto em memória incompleto. Campos ausentes: {', '.join(ausentes)}.",
                gate_parada=0, gates={}, penalidades=[], alertas=[],
                confiabilidade=0, preco=None, pvp=None, dy_12m=None,
                margem=None, margem_stress=None, preco_justo=None,
                preco_entrada=None, preco_stress_val=None, dy_recorrente=None,
                pct_rec=None, premio_cdi=None, vacancia=None, liquidez=None,
                segmento="INDEFINIDO", meses_hist=0, score_ia=score_ia,
                riscos_ia=riscos_ia, tom_gestor=tom_gestor, ia_status=ia_status
            )

    ind, fii_info = _carregar_base_decisao(ticker, contexto)

    if not ind or not fii_info or not ind.get("preco"):
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

    if contexto and "score_confianca" in contexto:
        confiabilidade = contexto["score_confianca"]
    else:
        confiabilidade = calcular_confiabilidade(ticker)

    margem          = calcular_margem_seguranca(ticker, contexto=contexto)
    margem_stress   = calcular_margem_seguranca(ticker, cenario_stress=True, contexto=contexto)
    dy_recorrente   = calcular_dy_recorrente(ticker, preco, contexto=contexto) if preco else None

    if contexto and "recorrencia_dividendos_pct" in contexto:
        # Garante a escala decimal correta (ex: 0.70) do recorrencia_dividendos_pct (Achado 6)
        pct_rec = contexto["recorrencia_dividendos_pct"]
    else:
        pct_rec = percentual_recorrente(ticker)

    premio_cdi      = calcular_premio(dy_recorrente, contexto=contexto)

    if contexto and "meses_historico" in contexto:
        meses_hist = contexto["meses_historico"]
    else:
        meses_hist = _meses_historico(ticker)

    if contexto and "quedas_consecutivas" in contexto:
        quedas_consec = contexto["quedas_consecutivas"]
    else:
        quedas_consec = _queda_dividendos_consecutivos(ticker)

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
    g0 = _gate0_validacao(ticker, ind, fii_info, contexto=contexto)
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
    g3 = _gate3_qualidade_renda(ticker, ind, pct_rec, dy_recorrente, premio_cdi, quedas_consec, segmento)
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
    decisao, motivo = _gate7_veredito(gates, margem, confiabilidade, tom_gestor, ia_status, contexto=contexto)

    # Gate 5C - Trava de decisão por confiabilidade dos dados.
    # O score não é apenas informativo: ele limita a força máxima da decisão.
    if confiabilidade < 50:
        decisao = "BLOQUEADO_CONFIANCA"
        motivo = f"Score de confiança insuficiente ({confiabilidade}%). Decisão bloqueada até reforçar a qualidade dos dados."
        alertas.append("Gate 5C: decisão bloqueada por confiabilidade abaixo de 50%.")
    elif confiabilidade < 70 and decisao in ("COMPRAR", "COMPRAR_PARCIAL", "ENTRADA_FORTE", "ENTRADA_PARCIAL"):
        decisao = "MONITORAR"
        motivo = f"Score de confiança baixo ({confiabilidade}%). Ativo pode ser acompanhado, mas não libera entrada."
        alertas.append("Gate 5C: decisão limitada a MONITORAR por confiabilidade entre 50% e 69%.")
    elif confiabilidade < 90 and decisao in ("COMPRAR", "ENTRADA_FORTE"):
        decisao = "COMPRAR_PARCIAL"
        motivo = f"Score de confiança moderado ({confiabilidade}%). Entrada limitada a parcial até reforçar os dados."
        alertas.append("Gate 5C: decisão limitada a COMPRAR_PARCIAL por confiabilidade entre 70% e 89%.")

    if confiabilidade >= 90:
        confianca_dados = "ALTA"
    elif confiabilidade >= 70:
        confianca_dados = "MEDIA"
    elif confiabilidade >= 50:
        confianca_dados = "BAIXA"
    else:
        confianca_dados = "INSUFICIENTE"

    if ia_status == "OK":
        confianca_ia = "DISPONIVEL"
    elif ia_status in ("INDISPONIVEL", "NAO_EXECUTADA", None):
        confianca_ia = "INDISPONIVEL"
    else:
        confianca_ia = "LIMITADA"

    if confianca_dados == "ALTA" and confianca_ia == "DISPONIVEL":
        confianca = "ALTA"
    elif confianca_dados == "ALTA" and confianca_ia == "INDISPONIVEL":
        confianca = "ALTA_SEM_IA"
    elif confianca_dados == "MEDIA":
        confianca = "MEDIA"
    elif confianca_dados == "BAIXA":
        confianca = "BAIXA"
    else:
        confianca = "INSUFICIENTE"

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

    resultado["confianca_dados"] = confianca_dados
    resultado["confianca_ia"] = confianca_ia
    resultado["confianca_final"] = confianca

    # Reabre o objeto já montado para os anexos de dimensionamento/zonas
    if False:
        pass

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
                contexto=contexto,
            )
        except Exception:
            pass

        try:
            resultado["zonas_entrada"] = calcular_zonas(ticker, contexto=contexto)
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
    if confiabilidade >= 90:
        confianca_dados = "ALTA"
    elif confiabilidade >= 70:
        confianca_dados = "MEDIA"
    elif confiabilidade >= 50:
        confianca_dados = "BAIXA"
    else:
        confianca_dados = "INSUFICIENTE"

    if ia_status == "OK":
        confianca_ia = "DISPONIVEL"
    elif ia_status in ("INDISPONIVEL", "NAO_EXECUTADA", None):
        confianca_ia = "INDISPONIVEL"
    else:
        confianca_ia = "LIMITADA"

    if confianca is None:
        if confianca_dados == "ALTA" and confianca_ia == "DISPONIVEL":
            confianca = "ALTA"
        elif confianca_dados == "ALTA" and confianca_ia == "INDISPONIVEL":
            confianca = "ALTA_SEM_IA"
        elif confianca_dados == "MEDIA":
            confianca = "MEDIA"
        elif confianca_dados == "BAIXA":
            confianca = "BAIXA"
        else:
            confianca = "INSUFICIENTE"

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
        "confianca_dados": confianca_dados,
        "confianca_ia":    confianca_ia,
        "confianca_final": confianca,

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
            str(n): g
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
