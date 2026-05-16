"""
coleta/api_yfinance.py
Coleta o histórico de preços e dividendos usando Yahoo Finance.

Uso no FIIA:
- dividendos: fallback, quando FNET não estiver disponível;
- preço: fonte rastreável com timestamp para reduzir decisão sobre preço obsoleto;
- histórico: suporte ao backtest.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import yfinance as yf

from banco import db
from processamento.dividendo_recorrente import classificar_dividendos
from sistema import observabilidade


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_get(row, chave: str, padrao=None):
    try:
        return row[chave]
    except Exception:
        return padrao


def _garantir_coluna(nome_tabela: str, nome_coluna: str, definicao: str) -> None:
    colunas = db.buscar_todos(f"PRAGMA table_info({nome_tabela})")
    existentes = {_row_get(col, "name") for col in colunas}
    if nome_coluna not in existentes:
        db.executar(f"ALTER TABLE {nome_tabela} ADD COLUMN {nome_coluna} {definicao}")


def garantir_campos_preco() -> None:
    """Garante rastreabilidade de preço na tabela indicadores."""
    _garantir_coluna("indicadores", "preco_timestamp", "TEXT")
    _garantir_coluna("indicadores", "preco_fonte", "TEXT")
    _garantir_coluna("indicadores", "preco_moeda", "TEXT")


def coletar_preco_atual(ticker: str) -> dict:
    """
    Coleta preço atual rastreável via yfinance e atualiza o snapshot diário.

    Mantém os demais indicadores intactos. Se já existir linha do dia para o ativo,
    atualiza apenas campos de preço/rastreabilidade; se não existir, cria snapshot
    mínimo para o dia.
    """
    garantir_campos_preco()
    ticker_norm = ticker.upper().replace(".SA", "").strip()
    agora = _agora_iso()
    hoje = datetime.now(timezone.utc).date().isoformat()

    try:
        ativo = yf.Ticker(f"{ticker_norm}.SA")
        preco = None
        moeda = "BRL"
        fonte_detalhe = "yfinance.fast_info"

        try:
            fast = ativo.fast_info
            preco = getattr(fast, "last_price", None) or fast.get("last_price")
            moeda = getattr(fast, "currency", None) or fast.get("currency") or moeda
        except Exception:
            preco = None

        if preco is None:
            fonte_detalhe = "yfinance.history_1d"
            hist = ativo.history(period="1d")
            if not hist.empty:
                preco = float(hist.iloc[-1]["Close"])

        if preco is None:
            raise ValueError("Preço indisponível no yfinance.")

        existente = db.buscar_um(
            "SELECT id FROM indicadores WHERE ticker = ? AND data = ? LIMIT 1",
            (ticker_norm, hoje),
        )
        if existente:
            db.executar(
                """
                UPDATE indicadores
                SET preco = ?, preco_timestamp = ?, preco_fonte = ?, preco_moeda = ?, fonte = COALESCE(fonte, ?), coletado_em = ?
                WHERE ticker = ? AND data = ?
                """,
                (float(preco), agora, fonte_detalhe, moeda, "yfinance", agora, ticker_norm, hoje),
            )
        else:
            db.executar(
                """
                INSERT INTO indicadores (ticker, data, preco, preco_timestamp, preco_fonte, preco_moeda, fonte, coletado_em)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ticker_norm, hoje, float(preco), agora, fonte_detalhe, moeda, "yfinance", agora),
            )

        resultado = {
            "ticker": ticker_norm,
            "preco": float(preco),
            "preco_timestamp": agora,
            "preco_fonte": fonte_detalhe,
            "preco_moeda": moeda,
        }
        observabilidade.registrar_evento(
            "INFO",
            "coleta.api_yfinance",
            "Preço atual yfinance coletado com timestamp",
            ticker=ticker_norm,
            contexto=resultado,
        )
        return resultado

    except Exception as e:
        observabilidade.registrar_erro(
            "coleta.api_yfinance",
            e,
            ticker=ticker_norm,
            fonte="yfinance",
            contexto={"funcao": "coletar_preco_atual"},
        )
        print(f"[yfinance] Erro ao puxar preço atual de {ticker_norm}: {e}")
        return {"ticker": ticker_norm, "erro": str(e)}


def coletar_historico_dividendos(ticker: str) -> None:
    """
    Baixa os dividendos de um FII pelo yfinance e armazena no banco de dados.
    Fallback: FNET deve prevalecer quando houver dado oficial.
    """
    try:
        ticker_norm = ticker.upper().replace(".SA", "").strip()
        ativo = yf.Ticker(f"{ticker_norm}.SA")

        try:
            divs = ativo.dividends
        except Exception:
            print(f"[yfinance] Aviso: {ticker_norm} parece estar deslistado ou não foi encontrado no Yahoo.")
            return

        if divs is None or divs.empty:
            print(f"[yfinance] Nenhum dividendo encontrado para {ticker_norm}.")
            return

        try:
            tz = divs.index.tz
            data_limite = pd.Timestamp.now(tz=tz) - pd.DateOffset(years=5)
        except Exception:
            data_limite = pd.Timestamp.now() - pd.DateOffset(years=5)

        divs = divs[divs.index >= data_limite]

        for data_pagto, valor in divs.items():
            data_str = data_pagto.strftime("%Y-%m-%d")
            oficial = db.buscar_um(
                """
                SELECT id FROM dividendos
                WHERE ticker = ? AND data_pagamento = ? AND fonte = 'FNET_AVISO_COTISTAS'
                LIMIT 1
                """,
                (ticker_norm, data_str),
            )
            if oficial:
                continue

            registro = {
                "ticker": ticker_norm,
                "data_pagamento": data_str,
                "valor": float(valor),
                "tipo": "INDEFINIDO",
                "fonte": "yfinance",
            }
            db.upsert("dividendos", registro)

        print(f"[yfinance] Histórico de dividendos do {ticker_norm} atualizado com {len(divs)} pagamentos.")
        classificar_dividendos(ticker_norm)

    except Exception as e:
        print(f"[yfinance] Erro ao puxar dividendos de {ticker}: {e}")


def pegar_preco_historico(ticker: str, data_alvo: str) -> Optional[float]:
    """
    Retorna o preço de fechamento ajustado do ativo numa data específica.
    """
    try:
        ticker_norm = ticker.upper().replace(".SA", "").strip()
        ativo = yf.Ticker(f"{ticker_norm}.SA")
        historico = ativo.history(start=data_alvo, period="5d")
        if not historico.empty:
            return float(historico.iloc[0]["Close"])
    except Exception as e:
        print(f"[yfinance] Erro ao buscar preço histórico para {ticker} em {data_alvo}: {e}")

    return None
