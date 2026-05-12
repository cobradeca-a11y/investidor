"""
mercado/semaforo_macro.py
Semaforo macro para condicionar o radar ao momento do ciclo.

VERMELHO → ambiente hostil para FIIs (reduzir exposicao)
AMARELO  → ambiente neutro (seletivo por segmento)
VERDE    → ambiente favoravel (aumentar exposicao)

Alimenta o Gate 0 do radar. Se VERMELHO, radar ainda roda mas
decisoes maximas ficam em AGUARDAR (sem COMPRAR automatico).
"""

from coleta.api_bcb import obter_selic_atual, obter_ipca_atual
import banco.db as db

# Limiares
_SELIC_HOSTIL   = 13.5   # % aa — acima disso renda fixa domina
_SELIC_NEUTRO   = 11.0   # % aa — abaixo disso FIIs competitivos
_SPREAD_MINIMO  = 3.0    # pp acima da SELIC para FII valer o risco


def calcular_spread_medio() -> float | None:
    """
    Calcula o DY medio dos FIIs no banco vs SELIC atual.
    Spread positivo = FIIs pagam acima da renda fixa.
    """
    selic = obter_selic_atual()
    if not selic:
        return None

    rows = db.buscar_todos(
        """
        SELECT dy_12m FROM indicadores
        WHERE dy_12m IS NOT NULL AND dy_12m > 0
        ORDER BY data DESC
        """
    )
    if not rows:
        return None

    dys = [r['dy_12m'] * 100 for r in rows]
    dy_medio = sum(dys) / len(dys)
    return round(dy_medio - selic, 2)


def tendencia_selic(janela_meses: int = 3) -> str:
    """
    Detecta se a SELIC esta em alta, queda ou estavel
    comparando o valor atual com a media dos ultimos N meses.
    """
    rows = db.buscar_todos(
        """
        SELECT selic FROM macro
        WHERE selic IS NOT NULL
        ORDER BY data DESC LIMIT ?
        """,
        (janela_meses,)
    )
    if len(rows) < 2:
        return "ESTAVEL"

    atual   = rows[0]['selic']
    passado = rows[-1]['selic']

    if atual > passado + 0.5:
        return "ALTA"
    if atual < passado - 0.5:
        return "QUEDA"
    return "ESTAVEL"


def avaliar() -> dict:
    """
    Retorna o semaforo macro completo.

    {
        "cor":      "VERDE" | "AMARELO" | "VERMELHO",
        "selic":    float,
        "ipca":     float,
        "spread":   float,
        "tendencia": "ALTA" | "QUEDA" | "ESTAVEL",
        "motivo":   str,
        "teto_decisao": "COMPRAR" | "COMPRAR_PARCIAL" | "AGUARDAR"
    }
    """
    selic     = obter_selic_atual() or 0.0
    ipca      = obter_ipca_atual()  or 0.0
    spread    = calcular_spread_medio()
    tendencia = tendencia_selic()

    # Logica do semaforo
    if selic >= _SELIC_HOSTIL and tendencia == "ALTA":
        cor           = "VERMELHO"
        motivo        = f"SELIC em {selic:.1f}% aa com tendencia de alta. Renda fixa domina."
        teto_decisao  = "AGUARDAR"

    elif selic >= _SELIC_HOSTIL and tendencia != "QUEDA":
        cor           = "AMARELO"
        motivo        = f"SELIC alta ({selic:.1f}% aa) mas sem tendencia clara. Ser seletivo."
        teto_decisao  = "COMPRAR_PARCIAL"

    elif selic < _SELIC_NEUTRO or tendencia == "QUEDA":
        if spread and spread >= _SPREAD_MINIMO:
            cor          = "VERDE"
            motivo       = f"SELIC em {selic:.1f}% aa com spread de {spread:.1f}pp. FIIs competitivos."
            teto_decisao = "COMPRAR"
        else:
            cor          = "AMARELO"
            motivo       = f"SELIC em queda mas spread ({spread:.1f}pp) ainda insuficiente."
            teto_decisao = "COMPRAR_PARCIAL"

    else:
        cor          = "AMARELO"
        motivo       = f"Ambiente neutro. SELIC {selic:.1f}% aa, spread {spread:.1f}pp."
        teto_decisao = "COMPRAR_PARCIAL"

    return {
        "cor":          cor,
        "selic":        selic,
        "ipca":         ipca,
        "spread":       spread,
        "tendencia":    tendencia,
        "motivo":       motivo,
        "teto_decisao": teto_decisao,
    }


def teto_decisao() -> str:
    """Atalho: retorna apenas o teto de decisao para uso no motor."""
    return avaliar()["teto_decisao"]
