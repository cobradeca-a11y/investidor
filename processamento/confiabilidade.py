"""
processamento/confiabilidade.py
Avalia a qualidade dos dados disponíveis para um FII.
Score 0-100. Abaixo de 60 bloqueia entrada pelo sistema.
"""
from typing import Optional
from banco import db
from config.settings import CONFIABILIDADE_MINIMA


def calcular_score(ticker: str) -> int:
    """
    Calcula score de confiabilidade com base nos dados mais recentes.
    Leva em conta: completude, atualização e consistência.
    """
    ind = db.buscar_um(
        """
        SELECT * FROM indicadores
        WHERE ticker = ?
        ORDER BY data DESC LIMIT 1
        """,
        (ticker,)
    )

    if not ind:
        return 0

    pontos = 0

    # Completude dos campos (60 pontos possíveis)
    campos_peso = {
        "preco":               20,
        "pvp":                 15,
        "dy_12m":              15,
        "liquidez_diaria":     10,
        "ultimo_dividendo":    10,
        "patrimonio_liquido":  10,
        "vacancia_fisica":      5,
        "vacancia_financeira":  5,
        "vpa":                  5,
        "dy_3m":                5,
    }
    for campo, peso in campos_peso.items():
        if ind[campo] is not None:
            pontos += peso

    # Atualização dos dados (20 pontos)
    from datetime import date, datetime
    data_dado = datetime.strptime(ind["data"], "%Y-%m-%d").date()
    dias_atraso = (date.today() - data_dado).days
    if dias_atraso == 0:
        pontos += 20
    elif dias_atraso <= 1:
        pontos += 15
    elif dias_atraso <= 3:
        pontos += 10
    elif dias_atraso <= 7:
        pontos += 5

    # Histórico de dividendos (20 pontos)
    qtd_div = db.buscar_um(
        "SELECT COUNT(*) as qtd FROM dividendos WHERE ticker = ?",
        (ticker,)
    )
    qtd = qtd_div["qtd"] if qtd_div else 0
    if qtd >= 24:
        pontos += 20
    elif qtd >= 12:
        pontos += 15
    elif qtd >= 6:
        pontos += 10
    elif qtd >= 3:
        pontos += 5

    return min(pontos, 100)


def dados_suficientes(ticker: str) -> bool:
    """Retorna True se a confiabilidade está acima do mínimo exigido."""
    return calcular_score(ticker) >= CONFIABILIDADE_MINIMA


def relatorio_confiabilidade(ticker: str) -> dict:
    """Retorna dict com score e diagnóstico legível."""
    score = calcular_score(ticker)
    ind = db.buscar_um(
        "SELECT * FROM indicadores WHERE ticker = ? ORDER BY data DESC LIMIT 1",
        (ticker,)
    )

    campos_ausentes = []
    if ind:
        for campo in ["preco", "pvp", "dy_12m", "liquidez_diaria",
                      "ultimo_dividendo", "patrimonio_liquido",
                      "vacancia_fisica", "vacancia_financeira"]:
            if ind[campo] is None:
                campos_ausentes.append(campo)

    nivel = (
        "EXCELENTE" if score >= 90 else
        "BOM"       if score >= 75 else
        "SUFICIENTE" if score >= 60 else
        "FRACO"     if score >= 40 else
        "INSUFICIENTE"
    )

    return {
        "ticker":          ticker,
        "score":           score,
        "nivel":           nivel,
        "suficiente":      score >= CONFIABILIDADE_MINIMA,
        "campos_ausentes": campos_ausentes,
    }
