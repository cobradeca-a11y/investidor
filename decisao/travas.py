"""
decisao/travas.py
Travas absolutas de segurança.
Se qualquer trava grave for acionada, o status máximo é MONITORAR.
Nenhum score alto supera uma trava.
"""
from typing import Optional
from config.settings import (
    LIQUIDEZ_MINIMA_DIARIA,
    CONFIABILIDADE_MINIMA,
    HISTORICO_MINIMO_MESES,
    PERCENTUAL_RECORRENTE_MINIMO,
    PREMIO_CDI_MINIMO,
)


def verificar_travas(
    ticker: str,
    confiabilidade: int,
    liquidez: Optional[float],
    margem_seguranca: Optional[float],
    premio_cdi: Optional[float],
    percentual_recorrente: Optional[float],
    tipo_fundo: str,
    meses_historico: int,
    score_qualidade: Optional[float],
    queda_dividendos_consecutivos: int = 0,
) -> list[dict]:
    """
    Verifica todas as travas e retorna lista de travas acionadas.
    Cada item: {"nome": str, "motivo": str, "bloqueia_entrada": bool}
    """
    travas_acionadas = []

    def _trava(nome: str, condicao: bool, motivo: str, bloqueia: bool = True):
        if condicao:
            travas_acionadas.append({
                "nome":             nome,
                "motivo":           motivo,
                "bloqueia_entrada": bloqueia,
            })

    _trava(
        "DADOS_INSUFICIENTES",
        confiabilidade < CONFIABILIDADE_MINIMA,
        f"Confiabilidade dos dados em {confiabilidade}% (mínimo: {CONFIABILIDADE_MINIMA}%). "
        "Muitos indicadores importantes estão ausentes ou desatualizados."
    )

    _trava(
        "LIQUIDEZ_BAIXA",
        liquidez is not None and liquidez < LIQUIDEZ_MINIMA_DIARIA,
        f"Liquidez diária de R$ {liquidez:,.0f} está abaixo do mínimo de "
        f"R$ {LIQUIDEZ_MINIMA_DIARIA:,.0f}. Posição difícil de montar e desmontar."
    )

    _trava(
        "LIQUIDEZ_AUSENTE",
        liquidez is None,
        "Liquidez diária não disponível. Impossível avaliar risco de entrada."
    )

    _trava(
        "MARGEM_NEGATIVA",
        margem_seguranca is not None and margem_seguranca < 0,
        f"Margem de segurança negativa ({margem_seguranca:.1%}). "
        "O preço atual está acima do considerado seguro para o risco desse ativo."
    )

    _trava(
        "PREMIO_CDI_INSUFICIENTE",
        premio_cdi is not None and premio_cdi < PREMIO_CDI_MINIMO,
        f"Prêmio sobre o CDI de {premio_cdi:.2f} pp está abaixo do mínimo de "
        f"{PREMIO_CDI_MINIMO} pp. Renda fixa remunera melhor com menos risco."
    )

    _trava(
        "DY_NAO_RECORRENTE",
        percentual_recorrente is not None and percentual_recorrente < PERCENTUAL_RECORRENTE_MINIMO,
        f"Apenas {percentual_recorrente:.0%} do dividendo é recorrente "
        f"(mínimo: {PERCENTUAL_RECORRENTE_MINIMO:.0%}). "
        "DY pode estar inflado por distribuições extraordinárias não sustentáveis."
    )

    _trava(
        "HISTORICO_INSUFICIENTE",
        meses_historico < HISTORICO_MINIMO_MESES,
        f"Fundo com apenas {meses_historico} meses de histórico "
        f"(mínimo: {HISTORICO_MINIMO_MESES} meses). "
        "Impossível avaliar consistência e comportamento em ciclos."
    )

    _trava(
        "QUALIDADE_BAIXA",
        score_qualidade is not None and score_qualidade < 40,
        f"Score de qualidade de {score_qualidade:.0f}/100 está abaixo do mínimo aceitável."
    )

    _trava(
        "QUEDA_DIVIDENDOS",
        queda_dividendos_consecutivos >= 3,
        f"Dividendos em queda por {queda_dividendos_consecutivos} meses consecutivos "
        "sem justificativa identificada. Sinal de deterioração da renda."
    )

    _trava(
        "FUNDO_DESENVOLVIMENTO",
        tipo_fundo == "DESENVOLVIMENTO",
        "Fundos de desenvolvimento têm risco estruturalmente diferente e "
        "não recebem status de ENTRADA automático. Avaliação humana obrigatória.",
        bloqueia=True
    )

    return travas_acionadas


def status_maximo_permitido(travas: list[dict]) -> str:
    """
    Se há travas ativas, o status máximo é MONITORAR.
    Se não há travas, qualquer status é permitido.
    """
    graves = [t for t in travas if t["bloqueia_entrada"]]
    if graves:
        return "MONITORAR"
    return "ENTRADA_SEGURA"  # sem restrição de teto
