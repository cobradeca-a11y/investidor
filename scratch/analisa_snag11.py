import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from banco import db
from coleta.api_fundamentus import coletar_fii
from coleta.api_yfinance import coletar_historico_dividendos
from decisao.motor_decisao import decidir
from pprint import pprint

ticker = 'SNAG11'

print(f'1. Coletando dados base do {ticker} (Fundamentus)...')
try:
    dados_fii = coletar_fii(ticker)
    print('Fundamentus retornou:', dados_fii)
except Exception as e:
    print('Erro Fundamentus:', e)

print(f'\n2. Coletando histórico de dividendos do {ticker} (Yahoo Finance)...')
try:
    coletar_historico_dividendos(ticker)
    print('Histórico coletado.')
except Exception as e:
    print('Erro Yahoo:', e)

print('\n3. Simulando Motor de Decisão...')
try:
    resultado = decidir(ticker)
    
    print(f'\nDecisão Final: {resultado.get("decisao")}')
    print(f'Motivo: {resultado.get("motivo")}')
    print(f'Gate de Parada: {resultado.get("gate_parada")}')
    print(f'Margem: {resultado.get("margem")} %')
    print(f'Preço Justo: R$ {resultado.get("preco_justo")}')
    print(f'Preço Atual: R$ {resultado.get("preco_atual")}')
    
    print('\nTrilha de Gates:')
    for t in resultado.get('trilha_gates', []):
        print(f'  {t}')
        
    print('\nZonas de Entrada:')
    pprint(resultado.get('zonas_entrada'))
    
except Exception as e:
    import traceback
    print(f'Erro ao simular decisão:')
    traceback.print_exc()
