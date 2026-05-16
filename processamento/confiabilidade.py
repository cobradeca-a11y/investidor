"""
processamento/confiabilidade.py
Avalia a qualidade dos dados disponíveis para um FII.
Score 0-100. Abaixo de 60 bloqueia entrada pelo sistema.

Regra crítica:
- preço com timestamp superior a 2 dias recebe teto de confiabilidade;
- preço sem timestamp também recebe teto, pois não é auditável.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from banco import db
from config.settings import CONFIABILIDADE_MINIMA

_TETO_PRECO_SEM_TIMESTAMP = 65
_TETO_PRECO_STALE_2D = 55


def _row_get(row, chave: str, padrao=None):
    try:
        return row[chave]
    except Exception:
        return padrao


def _parse_timestamp(valor: str | None) -> datetime | None:
    if not valor:
        return None
    texto = str(valor).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(texto)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _idade_preco_dias(ind) -> int | None:
    ts = _parse_timestamp(_row_get(ind, "preco_timestamp"))
    if not ts:
        return None
    agora = datetime.now(timezone.utc)
    return max(0, (agora - ts).days)


def _aplicar_teto_preco(score: int, ind) -> tuple[int, list[str]]:
    alertas: list[str] = []
    if _row_get(ind, "preco") is None:
        return score, alertas

    idade = _idade_preco_dias(ind)
    if idade is None:
        score = min(score, _TETO_PRECO_SEM_TIMESTAMP)
        alertas.append(
            f"Preço sem timestamp rastreável; confiabilidade limitada a {_TETO_PRECO_SEM_TIMESTAMP}."
        )
    elif idade > 2:
        score = min(score, _TETO_PRECO_STALE_2D)
        alertas.append(
            f"Preço desatualizado há {idade} dias; confiabilidade limitada a {_TETO_PRECO_STALE_2D}."
        )
    return score, alertas


def calcular_score(ticker: str) -> int:
    ticker_norm = ticker.upper().replace(".SA", "")
    ind = db.buscar_um(
        """
        SELECT * FROM indicadores
        WHERE ticker = ?
        ORDER BY data DESC LIMIT 1
        """,
        (ticker_norm,),
    )

    if not ind:
        return 0

    pontos = 0

    campos_peso = {
        "preco": 20,
        "pvp": 15,
        "dy_12m": 15,
        "liquidez_diaria": 10,
        "ultimo_dividendo": 10,
        "patrimonio_liquido": 10,
        "vacancia_fisica": 5,
        "vacancia_financeira": 5,
        "vpa": 5,
        "dy_3m": 5,
    }

    for campo, peso in campos_peso.items():
        if _row_get(ind, campo) is not None:
            pontos += peso

    try:
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
    except Exception:
        pass

    qtd_div = db.buscar_um(
        "SELECT COUNT(*) as qtd FROM dividendos WHERE ticker = ?",
        (ticker_norm,),
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

    score = min(pontos, 100)
    score, _ = _aplicar_teto_preco(score, ind)
    return score


def dados_suficientes(ticker: str) -> bool:
    return calcular_score(ticker) >= CONFIABILIDADE_MINIMA


def relatorio_confiabilidade(ticker: str) -> dict:
    """Retorna dict com score efetivo e diagnóstico legível."""
    ticker_norm = ticker.upper().replace(".SA", "")

    ind = db.buscar_um(
        "SELECT * FROM indicadores WHERE ticker = ? ORDER BY data DESC LIMIT 1",
        (ticker_norm,),
    )

    campos_ausentes = []
    alertas = []
    idade_preco = None

    if ind:
        for campo in [
            "preco",
            "pvp",
            "dy_12m",
            "liquidez_diaria",
            "ultimo_dividendo",
            "patrimonio_liquido",
            "vacancia_fisica",
            "vacancia_financeira",
        ]:
            if _row_get(ind, campo) is None:
                campos_ausentes.append(campo)

        idade_preco = _idade_preco_dias(ind)

    score = calcular_score(ticker_norm)

    if ind:
        score, alertas = _aplicar_teto_preco(score, ind)

    nivel = (
        "EXCELENTE" if score >= 90 else
        "BOM" if score >= 75 else
        "SUFICIENTE" if score >= 60 else
        "FRACO" if score >= 40 else
        "INSUFICIENTE"
    )

    return {
        "ticker": ticker_norm,
        "score": score,
        "nivel": nivel,
        "suficiente": score >= CONFIABILIDADE_MINIMA,
        "campos_ausentes": campos_ausentes,
        "idade_preco_dias": idade_preco,
        "preco_timestamp": _row_get(ind, "preco_timestamp") if ind else None,
        "preco_fonte": _row_get(ind, "preco_fonte") if ind else None,
        "alertas": alertas,
    }
