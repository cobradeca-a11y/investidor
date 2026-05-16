"""
operacional/saude_fontes.py

Painel operacional de saúde das fontes do FIIA.
Mostra onde o motor está usando dado forte, fallback ou dado ausente.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from banco import db
from sistema import observabilidade


def _row_get(row: Any, chave: str, padrao: Any = None) -> Any:
    try:
        return row[chave]
    except Exception:
        return padrao


def _idade_dias(data_txt: str | None) -> int | None:
    if not data_txt:
        return None
    try:
        data_base = datetime.fromisoformat(str(data_txt).replace("Z", "+00:00")).date()
    except Exception:
        try:
            data_base = datetime.strptime(str(data_txt)[:10], "%Y-%m-%d").date()
        except Exception:
            return None
    return max(0, (date.today() - data_base).days)


def gerar_painel_saude_fontes() -> dict[str, Any]:
    ativos = db.buscar_todos("SELECT ticker, segmento FROM fiis WHERE COALESCE(ativo, 1) = 1 ORDER BY ticker")

    detalhes = []
    resumo = {
        "ativos": len(ativos),
        "sem_indicadores": 0,
        "preco_desatualizado": 0,
        "preco_sem_timestamp": 0,
        "sem_dividendos": 0,
        "sem_fnet": 0,
        "sem_cvm_mensal": 0,
        "fallback_patrimonial": 0,
        "confiabilidade_baixa": 0,
    }

    for ativo in ativos:
        ticker = ativo["ticker"]
        ind = db.buscar_um("SELECT * FROM indicadores WHERE ticker = ? ORDER BY data DESC LIMIT 1", (ticker,))
        qtd_div = db.buscar_um("SELECT COUNT(*) AS qtd FROM dividendos WHERE ticker = ?", (ticker,))
        qtd_fnet = db.buscar_um("SELECT COUNT(*) AS qtd FROM fnet_dividendos_fii WHERE ticker = ?", (ticker,))
        qtd_cvm = db.buscar_um(
            """
            SELECT COUNT(*) AS qtd
            FROM cvm_informes_mensais_fii
            WHERE cnpj_fundo IN (SELECT cnpj FROM mapa_ticker_cnpj WHERE ticker = ?)
            """,
            (ticker,),
        )

        problemas = []
        idade_preco = None

        if not ind:
            resumo["sem_indicadores"] += 1
            problemas.append("SEM_INDICADORES")
        else:
            idade_preco = _idade_dias(_row_get(ind, "preco_timestamp") or _row_get(ind, "data"))
            if not _row_get(ind, "preco_timestamp"):
                resumo["preco_sem_timestamp"] += 1
                problemas.append("PRECO_SEM_TIMESTAMP")
            if idade_preco is not None and idade_preco > 2:
                resumo["preco_desatualizado"] += 1
                problemas.append("PRECO_DESATUALIZADO")
            if (_row_get(ind, "confiabilidade") or 0) < 60:
                resumo["confiabilidade_baixa"] += 1
                problemas.append("CONFIABILIDADE_BAIXA")

        if not qtd_div or int(qtd_div["qtd"] or 0) == 0:
            resumo["sem_dividendos"] += 1
            problemas.append("SEM_DIVIDENDOS")
        if not qtd_fnet or int(qtd_fnet["qtd"] or 0) == 0:
            resumo["sem_fnet"] += 1
            problemas.append("SEM_FNET")
        if not qtd_cvm or int(qtd_cvm["qtd"] or 0) == 0:
            resumo["sem_cvm_mensal"] += 1
            problemas.append("SEM_CVM_MENSAL")

        fonte_patrimonial = _row_get(ind, "fonte") if ind else None
        if not fonte_patrimonial or str(fonte_patrimonial).upper() not in {"CVM", "CVM_INF_MENSAL"}:
            resumo["fallback_patrimonial"] += 1
            problemas.append("FALLBACK_PATRIMONIAL")

        detalhes.append({
            "ticker": ticker,
            "segmento": ativo["segmento"],
            "idade_preco_dias": idade_preco,
            "confiabilidade": _row_get(ind, "confiabilidade") if ind else None,
            "qtd_dividendos": int(qtd_div["qtd"] or 0) if qtd_div else 0,
            "qtd_fnet": int(qtd_fnet["qtd"] or 0) if qtd_fnet else 0,
            "qtd_cvm_mensal": int(qtd_cvm["qtd"] or 0) if qtd_cvm else 0,
            "problemas": problemas,
        })

    painel = {"resumo": resumo, "detalhes": detalhes}
    observabilidade.registrar_evento(
        "INFO",
        "operacional.saude_fontes",
        "Painel de saúde das fontes gerado",
        contexto=resumo,
    )
    return painel
