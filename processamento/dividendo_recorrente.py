"""
processamento/dividendo_recorrente.py
Separa dividendo recorrente de extraordinário.
Regra: valores acima de 2 desvios padrão da mediana são marcados como EXTRAORDINARIO.
"""
import statistics
from typing import Optional
from banco import db


def classificar_dividendos(ticker: str) -> None:
    """
    Reclassifica os dividendos de um FII como RECORRENTE ou EXTRAORDINARIO
    com base na dispersão estatística dos pagamentos.

    Usa um único executemany + commit para garantir que todas as
    classificações sejam persistidas atomicamente.
    """
    rows = db.buscar_todos(
        "SELECT id, valor FROM dividendos WHERE ticker = ? ORDER BY data_pagamento",
        (ticker,)
    )
    if len(rows) < 3:
        return  # histórico insuficiente para classificar

    valores = [r["valor"] for r in rows]
    mediana = statistics.median(valores)
    try:
        desvio = statistics.stdev(valores)
    except statistics.StatisticsError:
        desvio = 0

    limite_extra = mediana + (2 * desvio)

    params = [
        ("EXTRAORDINARIO" if row["valor"] > limite_extra else "RECORRENTE", row["id"])
        for row in rows
    ]

    # Batch único: uma conexão, um commit explícito
    conn = db.conectar()
    try:
        conn.executemany("UPDATE dividendos SET tipo = ? WHERE id = ?", params)
        conn.commit()
    finally:
        conn.close()


def calcular_dy_recorrente(ticker: str, preco: Optional[float]) -> Optional[float]:
    """
    Calcula o DY anualizado usando a MEDIANA dos dividendos
    dos últimos 12 meses. A mediana expurga automaticamente picos absurdos.
    Retorna percentual anual (ex: 0.115 = 11,5% a.a.) ou None.
    """
    if not preco or preco <= 0:
        return None

    rows = db.buscar_todos(
        """
        SELECT valor FROM dividendos
        WHERE ticker = ?
          AND data_pagamento >= date('now', '-12 months')
        """,
        (ticker,)
    )

    if not rows or len(rows) < 3:
        return None  # histórico insuficiente

    valores = [r["valor"] for r in rows]
    mediana_mensal = statistics.median(valores)

    anual = (mediana_mensal * 12) / preco
    return round(anual, 6)


def percentual_recorrente(ticker: str) -> Optional[float]:
    """
    Retorna a fração do DY total que é recorrente (0 a 1).
    Ex: 0.85 = 85% do dividendo é recorrente.

    Garante que a classificação RECORRENTE/EXTRAORDINARIO esteja atualizada
    antes de consultar. Se houver registros INDEFINIDO, roda
    classificar_dividendos() automaticamente com commit explícito.
    """
    indefinidos = db.buscar_um(
        "SELECT COUNT(*) as qtd FROM dividendos WHERE ticker = ? AND tipo = 'INDEFINIDO'",
        (ticker,)
    )
    if indefinidos and indefinidos["qtd"] > 0:
        classificar_dividendos(ticker)

    total = db.buscar_um(
        """
        SELECT SUM(valor) as total FROM dividendos
        WHERE ticker = ?
          AND data_pagamento >= date('now', '-6 months')
        """,
        (ticker,)
    )
    recorrente = db.buscar_um(
        """
        SELECT SUM(valor) as total FROM dividendos
        WHERE ticker = ?
          AND tipo = 'RECORRENTE'
          AND data_pagamento >= date('now', '-6 months')
        """,
        (ticker,)
    )

    if not total or not total["total"] or total["total"] == 0:
        return None

    rec = recorrente["total"] if recorrente and recorrente["total"] else 0
    return round(rec / total["total"], 4)
