"""
coleta/api_yfinance.py
Coleta o histórico de preços e dividendos usando a API oficial do Yahoo Finance.
Essencial para cálculo de proventos recorrentes e Máquina do Tempo.
"""
import yfinance as yf
import pandas as pd
from datetime import date
from typing import Optional
from banco import db

def coletar_historico_dividendos(ticker: str) -> None:
    """
    Baixa os dividendos de um FII pelo yfinance e armazena no banco de dados.
    """
    try:
        ativo = yf.Ticker(f"{ticker}.SA")
        
        # Tenta acessar os dividendos. Em alguns casos de erro (ticker não existe), 
        # o yfinance pode lançar erros de atributo ou retornar None.
        try:
            divs = ativo.dividends
        except Exception:
            print(f"[yfinance] Aviso: {ticker} parece estar deslistado ou não foi encontrado no Yahoo.")
            return

        if divs is None or divs.empty:
            print(f"[yfinance] Nenhum dividendo encontrado para {ticker}.")
            return
            
        # Pega apenas os últimos 5 anos por segurança e lida com o timezone do yfinance
        try:
            tz = divs.index.tz
            data_limite = pd.Timestamp.now(tz=tz) - pd.DateOffset(years=5)
        except Exception:
            data_limite = pd.Timestamp.now() - pd.DateOffset(years=5)
            
        divs = divs[divs.index >= data_limite]
        
        # O index é um DateTimeIndex com Timezone. Vamos simplificar para data ISO (YYYY-MM-DD)
        for data_pagto, valor in divs.items():
            data_str = data_pagto.strftime("%Y-%m-%d")
            
            registro = {
                "ticker": ticker,
                "data_pagamento": data_str,
                "valor": float(valor),
                "tipo": "INDEFINIDO",
                "fonte": "yfinance"
            }
            db.upsert("dividendos", registro)
            
        print(f"[yfinance] Histórico de dividendos do {ticker} atualizado com {len(divs)} pagamentos.")
        
    except Exception as e:
        print(f"[yfinance] Erro ao puxar dividendos de {ticker}: {e}")


def pegar_preco_historico(ticker: str, data_alvo: str) -> Optional[float]:
    """
    Retorna o preço de fechamento ajustado do ativo numa data específica (para a Máquina do Tempo).
    """
    try:
        ativo = yf.Ticker(f"{ticker}.SA")
        # Baixa 5 dias de janela para garantir que pega um dia útil (usando period="5d")
        historico = ativo.history(start=data_alvo, period="5d")
        if not historico.empty:
            # Retorna o primeiro dia útil após (ou no próprio dia) da data alvo
            return float(historico.iloc[0]["Close"])
    except Exception as e:
        print(f"[yfinance] Erro ao buscar preço histórico para {ticker} em {data_alvo}: {e}")
        
    return None
