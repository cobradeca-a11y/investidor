"""
mercado/comparador_cdi.py
Compara o retorno do FII contra o CDI atual.
Calcula prêmio de risco e verifica se compensa o risco.
"""
from typing import Optional
from coleta.api_bcb import obter_cdi_atual
from config.settings import PREMIO_CDI_MINIMO


def calcular_premio(dy_recorrente_anual: Optional[float]) -> Optional[float]:
    """
    Calcula o prêmio do FII sobre o CDI.
    Ex: DY recorrente 11,5% - CDI 10,75% = prêmio de 0,75 pp
    Retorna diferença em pontos percentuais ou None.
    """
    if dy_recorrente_anual is None:
        return None

    cdi = obter_cdi_atual()
    if cdi is None:
        return None

    # CDI vem em % ao ano do BCB (ex: 10.75)
    # DY recorrente está em decimal (ex: 0.115 = 11.5%)
    dy_pct = dy_recorrente_anual * 100
    return round(dy_pct - cdi, 4)


def premio_suficiente(dy_recorrente_anual: Optional[float]) -> bool:
    """
    Retorna True se o prêmio sobre o CDI atinge o mínimo exigido.
    """
    premio = calcular_premio(dy_recorrente_anual)
    if premio is None:
        return False
    return premio >= PREMIO_CDI_MINIMO


def relatorio_vs_cdi(dy_recorrente_anual: Optional[float]) -> dict:
    """
    Retorna comparativo completo FII vs CDI para o relatório.
    """
    cdi = obter_cdi_atual()
    premio = calcular_premio(dy_recorrente_anual)

    dy_pct = (dy_recorrente_anual * 100) if dy_recorrente_anual else None

    if premio is None:
        avaliacao = "NÃO CALCULÁVEL"
        explicacao = "Não foi possível calcular o prêmio (dados insuficientes)."
    elif premio >= PREMIO_CDI_MINIMO * 2:
        avaliacao = "EXCELENTE"
        explicacao = f"Prêmio de {premio:.2f} pp acima do CDI — compensação muito boa para o risco."
    elif premio >= PREMIO_CDI_MINIMO:
        avaliacao = "ADEQUADO"
        explicacao = f"Prêmio de {premio:.2f} pp acima do CDI — compensação aceitável para o risco."
    elif premio >= 0:
        avaliacao = "INSUFICIENTE"
        explicacao = f"Prêmio de apenas {premio:.2f} pp — risco de FII não está sendo bem remunerado vs renda fixa."
    else:
        avaliacao = "NEGATIVO"
        explicacao = f"Renda fixa está pagando {abs(premio):.2f} pp a mais que esse FII, com menos risco."

    return {
        "dy_recorrente_pct":    dy_pct,
        "cdi_atual_pct":        cdi,
        "premio_pp":            premio,
        "avaliacao":            avaliacao,
        "suficiente":           premio is not None and premio >= PREMIO_CDI_MINIMO,
        "explicacao":           explicacao,
    }
