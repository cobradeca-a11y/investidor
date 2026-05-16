"""
mercado/semaforo_macro.py
Semaforo macro para condicionar o radar ao momento do ciclo.
"""

from coleta.api_bcb import obter_selic_atual, obter_ipca_atual
import banco.db as db

_SELIC_HOSTIL = 13.5
_SELIC_NEUTRO = 11.0
_SPREAD_MINIMO = 3.0
_JANELA_SPREAD_DIAS = 30


def _buscar_dy_por_ticker_recente(janela_dias: int):
    return db.buscar_todos(
        """
        SELECT i.ticker, i.dy_12m, i.data
        FROM indicadores i
        JOIN (
            SELECT ticker, MAX(data) AS data_max
            FROM indicadores
            WHERE dy_12m IS NOT NULL
              AND dy_12m > 0
              AND data >= date('now', ?)
            GROUP BY ticker
        ) ult ON ult.ticker = i.ticker AND ult.data_max = i.data
        WHERE i.dy_12m IS NOT NULL AND i.dy_12m > 0
        """,
        (f"-{int(janela_dias)} days",),
    )


def _buscar_dy_por_ticker_fallback(limite: int = 100):
    return db.buscar_todos(
        """
        SELECT i.ticker, i.dy_12m, i.data
        FROM indicadores i
        JOIN (
            SELECT ticker, MAX(data) AS data_max
            FROM indicadores
            WHERE dy_12m IS NOT NULL AND dy_12m > 0
            GROUP BY ticker
        ) ult ON ult.ticker = i.ticker AND ult.data_max = i.data
        WHERE i.dy_12m IS NOT NULL AND i.dy_12m > 0
        ORDER BY i.data DESC
        LIMIT ?
        """,
        (limite,),
    )


def calcular_spread_medio(janela_dias: int = _JANELA_SPREAD_DIAS) -> float | None:
    """
    Calcula o DY médio recente dos FIIs no banco vs SELIC atual.
    Cada ticker contribui apenas uma vez com seu snapshot mais recente.
    """
    selic = obter_selic_atual()
    if not selic:
        return None

    rows = _buscar_dy_por_ticker_recente(janela_dias)
    if not rows:
        rows = _buscar_dy_por_ticker_fallback(100)
    if not rows:
        return None

    dys = [r["dy_12m"] * 100 for r in rows]
    dy_medio = sum(dys) / len(dys)
    return round(dy_medio - selic, 2)


def tendencia_selic(janela_meses: int = 3) -> str:
    rows = db.buscar_todos(
        """
        SELECT selic FROM macro
        WHERE selic IS NOT NULL
        ORDER BY data DESC LIMIT ?
        """,
        (janela_meses,),
    )
    if len(rows) < 2:
        return "ESTAVEL"

    atual = rows[0]["selic"]
    passado = rows[-1]["selic"]

    if atual > passado + 0.5:
        return "ALTA"
    if atual < passado - 0.5:
        return "QUEDA"
    return "ESTAVEL"


def avaliar() -> dict:
    selic = obter_selic_atual() or 0.0
    ipca = obter_ipca_atual() or 0.0
    spread = calcular_spread_medio()
    tendencia = tendencia_selic()

    if selic >= _SELIC_HOSTIL and tendencia == "ALTA":
        cor = "VERMELHO"
        motivo = f"SELIC em {selic:.1f}% aa com tendencia de alta. Renda fixa domina."
        teto_decisao = "AGUARDAR"
    elif selic >= _SELIC_HOSTIL and tendencia != "QUEDA":
        cor = "AMARELO"
        motivo = f"SELIC alta ({selic:.1f}% aa) mas sem tendencia clara. Ser seletivo."
        teto_decisao = "COMPRAR_PARCIAL"
    elif selic < _SELIC_NEUTRO or tendencia == "QUEDA":
        if spread is not None and spread >= _SPREAD_MINIMO:
            cor = "VERDE"
            motivo = f"SELIC em {selic:.1f}% aa com spread recente de {spread:.1f}pp. FIIs competitivos."
            teto_decisao = "COMPRAR"
        else:
            spread_txt = f"{spread:.1f}pp" if spread is not None else "indisponível"
            cor = "AMARELO"
            motivo = f"SELIC em queda mas spread recente ({spread_txt}) ainda insuficiente."
            teto_decisao = "COMPRAR_PARCIAL"
    else:
        spread_txt = f"{spread:.1f}pp" if spread is not None else "indisponível"
        cor = "AMARELO"
        motivo = f"Ambiente neutro. SELIC {selic:.1f}% aa, spread recente {spread_txt}."
        teto_decisao = "COMPRAR_PARCIAL"

    return {
        "cor": cor,
        "selic": selic,
        "ipca": ipca,
        "spread": spread,
        "janela_spread_dias": _JANELA_SPREAD_DIAS,
        "spread_agregado_por_ticker": True,
        "tendencia": tendencia,
        "motivo": motivo,
        "teto_decisao": teto_decisao,
    }


def teto_decisao() -> str:
    return avaliar()["teto_decisao"]
