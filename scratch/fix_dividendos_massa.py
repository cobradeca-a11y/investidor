
import sys
import os
sys.path.append(os.getcwd())

from banco import db
from processamento.dividendo_recorrente import classificar_dividendos

print("--- CLASSIFICAÇÃO EM MASSA ---")
tickers = db.buscar_todos("SELECT DISTINCT ticker FROM dividendos")
total = len(tickers)

for i, row in enumerate(tickers):
    ticker = row["ticker"]
    classificar_dividendos(ticker)
    if i % 10 == 0:
        print(f"[{i}/{total}] Processando {ticker}...")

print("\nVerificando ALZR11 após correção...")
rows = db.buscar_todos("SELECT ticker, valor, tipo FROM dividendos WHERE ticker = 'ALZR11' LIMIT 5")
for r in rows:
    print(dict(r))

print("\n--- FIM DA CLASSIFICAÇÃO ---")
