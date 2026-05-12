"""
aprendizado/avaliador.py
Avalia decisoes passadas em duas janelas de tempo.

Janela 90 dias  → avalia TIMING (era o momento certo?)
Janela 365 dias → avalia TESE   (a analise estava certa?)

Grava resultados em decisoes_resultado e atualiza versoes_modelo.
"""

from datetime import date, timedelta
from banco import db
from coleta.api_bcb import obter_selic_atual

_SQL_RESULTADO = """
CREATE TABLE IF NOT EXISTS decisoes_resultado (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    decisao_id          INTEGER NOT NULL,
    ticker              TEXT NOT NULL,
    janela_dias         INTEGER NOT NULL,
    data_avaliacao      TEXT NOT NULL,
    preco_entrada       REAL,
    preco_avaliacao     REAL,
    retorno_preco       REAL,
    retorno_dividendos  REAL,
    retorno_total       REAL,
    retorno_cdi_periodo REAL,
    acerto              INTEGER DEFAULT 0,
    tipo_resultado      TEXT,
    observacao          TEXT,
    criado_em           TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(decisao_id, janela_dias)
);
"""


def _garantir_tabela():
    db.executar(_SQL_RESULTADO)


def _cdi_periodo(dias: int) -> float:
    """CDI estimado para o periodo em %."""
    selic_anual = obter_selic_atual() or 10.75
    return round((1 + selic_anual / 100) ** (dias / 252) - 1, 4) * 100


def _dividendos_periodo(ticker: str, data_inicio: str, data_fim: str) -> float:
    """Soma dividendos pagos no periodo."""
    rows = db.buscar_todos(
        """
        SELECT SUM(valor) as total FROM dividendos
        WHERE ticker = ?
        AND data_pagamento >= ?
        AND data_pagamento <= ?
        """,
        (ticker, data_inicio, data_fim)
    )
    if rows and rows[0].get('total'):
        return float(rows[0]['total'])
    return 0.0


def _preco_na_data(ticker: str, data: str) -> float | None:
    """Preco mais proximo da data solicitada."""
    row = db.buscar_um(
        """
        SELECT preco FROM indicadores
        WHERE ticker = ? AND data <= ?
        ORDER BY data DESC LIMIT 1
        """,
        (ticker, data)
    )
    return row['preco'] if row and row.get('preco') else None


def avaliar_decisao(decisao_id: int, janela_dias: int) -> dict | None:
    """
    Avalia uma decisao especifica na janela de dias informada.
    Retorna None se a janela ainda nao se completou.
    """
    _garantir_tabela()

    decisao = db.buscar_um(
        "SELECT * FROM decisoes WHERE id = ?",
        (decisao_id,)
    )
    if not decisao:
        return None

    data_decisao = date.fromisoformat(decisao['data_decisao'])
    data_avaliacao = data_decisao + timedelta(days=janela_dias)

    if date.today() < data_avaliacao:
        return None  # janela ainda nao fechou

    ticker        = decisao['ticker']
    preco_entrada = decisao.get('preco_na_decisao') or decisao.get('preco_atual')
    preco_aval    = _preco_na_data(ticker, data_avaliacao.isoformat())

    if not preco_entrada or not preco_aval:
        return None

    dividendos    = _dividendos_periodo(ticker, decisao['data_decisao'], data_avaliacao.isoformat())
    retorno_preco = (preco_aval / preco_entrada - 1) * 100
    retorno_div   = (dividendos / preco_entrada) * 100
    retorno_total = retorno_preco + retorno_div
    cdi_periodo   = _cdi_periodo(janela_dias)
    acerto        = 1 if retorno_total > cdi_periodo else 0

    if janela_dias == 90:
        tipo = "TIMING"
        obs  = "Avaliacao de timing: o preco se comportou como esperado?"
    else:
        tipo = "TESE"
        obs  = "Avaliacao de tese: os fundamentos se mantiveram? A renda foi entregue?"

    db.executar(
        """
        INSERT OR REPLACE INTO decisoes_resultado
            (decisao_id, ticker, janela_dias, data_avaliacao, preco_entrada,
             preco_avaliacao, retorno_preco, retorno_dividendos, retorno_total,
             retorno_cdi_periodo, acerto, tipo_resultado, observacao)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            decisao_id, ticker, janela_dias, data_avaliacao.isoformat(),
            preco_entrada, preco_aval,
            round(retorno_preco, 2), round(retorno_div, 2), round(retorno_total, 2),
            round(cdi_periodo, 2), acerto, tipo, obs
        )
    )

    return {
        "decisao_id":     decisao_id,
        "ticker":         ticker,
        "janela_dias":    janela_dias,
        "retorno_total":  round(retorno_total, 2),
        "cdi_periodo":    round(cdi_periodo, 2),
        "acerto":         bool(acerto),
        "tipo":           tipo,
    }


def rodar_avaliacoes_pendentes() -> dict:
    """
    Varre todas as decisoes nao avaliadas e processa as janelas de 90 e 365 dias.
    """
    _garantir_tabela()

    decisoes = db.buscar_todos(
        "SELECT id, ticker, data_decisao FROM decisoes WHERE avaliada = 0"
    )

    total_90  = 0
    total_365 = 0

    for d in decisoes:
        for janela in [90, 365]:
            resultado = avaliar_decisao(d['id'], janela)
            if resultado:
                if janela == 90:
                    total_90 += 1
                else:
                    total_365 += 1

    print(f"[avaliador] {total_90} avaliacoes de 90d e {total_365} de 365d processadas.")
    return {"avaliadas_90d": total_90, "avaliadas_365d": total_365}


def taxa_acerto(janela_dias: int = 90) -> dict:
    """Retorna taxa de acerto geral e por segmento."""
    rows = db.buscar_todos(
        """
        SELECT r.acerto, f.segmento
        FROM decisoes_resultado r
        JOIN decisoes d ON r.decisao_id = d.id
        LEFT JOIN fiis f ON d.ticker = f.ticker
        WHERE r.janela_dias = ?
        """,
        (janela_dias,)
    )
    if not rows:
        return {"total": 0, "acerto_pct": 0, "por_segmento": {}}

    total  = len(rows)
    acertos = sum(1 for r in rows if r['acerto'])
    pct    = round(acertos / total * 100, 1)

    por_seg = {}
    for r in rows:
        seg = r.get('segmento') or 'INDEFINIDO'
        if seg not in por_seg:
            por_seg[seg] = {"total": 0, "acertos": 0}
        por_seg[seg]["total"]   += 1
        por_seg[seg]["acertos"] += r['acerto'] or 0

    for seg in por_seg:
        t = por_seg[seg]["total"]
        a = por_seg[seg]["acertos"]
        por_seg[seg]["pct"] = round(a / t * 100, 1) if t else 0

    return {
        "janela_dias":   janela_dias,
        "total":         total,
        "acerto_pct":    pct,
        "por_segmento":  por_seg,
    }
