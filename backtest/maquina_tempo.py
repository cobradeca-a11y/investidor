"""
backtest/maquina_tempo.py
O simulador de histórico. Volta no tempo, calcula os dados com base no passado,
toma a decisão pelo algoritmo e avança 1 ano para aferir resultado.
"""
from datetime import datetime, timedelta
import pandas as pd
from banco import db
from coleta.api_yfinance import pegar_preco_historico
from coleta.api_bcb import coletar_macro

def executar_backtest(ticker: str):
    print("\n" + "="*50)
    print(f"  MÁQUINA DO TEMPO: BACKTEST DE {ticker}")
    print("="*50)
    
    # Simula 5 anos atrás até 1 ano atrás
    hoje = datetime.now()
    anos_simulacao = [hoje.year - i for i in range(1, 6)]
    anos_simulacao.sort() # Ex: 2019, 2020, 2021, 2022, 2023
    
    print(f"Carregando histórico de {anos_simulacao[0]} a {anos_simulacao[-1]}...\n")
    
    acertos = 0
    total = 0
    
    # Para o backtest ficar super realista, teríamos que mockar o VPA de cada ano.
    # Mas como prova de conceito, focaremos na rentabilidade Cotação + DY.
    
    for ano in anos_simulacao:
        data_decisao = f"{ano}-01-10" # Começo do ano
        data_avaliacao = f"{ano+1}-01-10" # 1 ano depois
        
        preco_entrada = pegar_preco_historico(ticker, data_decisao)
        preco_saida = pegar_preco_historico(ticker, data_avaliacao)
        
        if not preco_entrada or not preco_saida:
            continue
            
        # Calcula dividendos nesse período de 1 ano
        divs = db.buscar_um(
            """
            SELECT SUM(valor) as total FROM dividendos 
            WHERE ticker = ? AND data_pagamento >= ? AND data_pagamento < ?
            """,
            (ticker, data_decisao, data_avaliacao)
        )
        
        div_total = divs["total"] if divs and divs["total"] else 0
        
        # Rentabilidade FII
        rentabilidade_cotas = (preco_saida / preco_entrada) - 1
        rentabilidade_div = div_total / preco_entrada
        rentabilidade_total = rentabilidade_cotas + rentabilidade_div
        
        # Como o CDI do backtest demandaria baixar o CDI histórico de 1 ano, 
        # fixamos uma métrica de exemplo (10% a.a) ou pegamos uma base simplificada.
        rentabilidade_cdi_estimada = 0.10 # 10%
        
        # Se rendeu mais que o CDI estimado, foi uma decisão de entrada correta
        foi_bom_negocio = rentabilidade_total > rentabilidade_cdi_estimada
        
        # Dividendos pagos no ano ANTERIOR à decisão (para simular a visão do investidor na época)
        data_ano_anterior = f"{ano-1}-01-10"
        divs_ant = db.buscar_um(
            "SELECT SUM(valor) as total FROM dividendos WHERE ticker = ? AND data_pagamento >= ? AND data_pagamento < ?",
            (ticker, data_ano_anterior, data_decisao)
        )
        div_total_ant = divs_ant["total"] if divs_ant and divs_ant["total"] else 0
        
        # Qual seria o DY esperado pelo investidor naquela época?
        dy_projetado = div_total_ant / preco_entrada if preco_entrada else 0
        
        # O algoritmo agora é dinâmico:
        # Só entra se o FII estiver pagando um DY projetado maior ou igual a uma meta conservadora (ex: 8%)
        meta_dy = 0.08 
        decisao_algoritmo = "ENTRADA_SEGURA" if dy_projetado >= meta_dy else "AGUARDAR"
        
        acerto = False
        if decisao_algoritmo == "ENTRADA_SEGURA" and foi_bom_negocio:
            acerto = True
        elif decisao_algoritmo != "ENTRADA_SEGURA" and not foi_bom_negocio:
            acerto = True
            
        if decisao_algoritmo == "ENTRADA_SEGURA":
            total += 1
            if acerto: acertos += 1
            
        status_acerto = "✅ Acertou" if acerto else "❌ Errou"
        
        print(f"Data: {data_decisao} | Preço: R${preco_entrada:.2f}")
        print(f"  → Recomendação FIIA: {decisao_algoritmo}")
        print(f"  → [1 ano depois] Preço: R${preco_saida:.2f} | Div: R${div_total:.2f}")
        print(f"  → Rentabilidade Total: {rentabilidade_total*100:.1f}% vs CDI (10.0%)")
        print(f"  → Avaliação do Algoritmo: {status_acerto}\n")
        
    print("="*50)
    print("  RELATÓRIO FINAL DO BACKTEST")
    print("="*50)
    if total > 0:
        taxa = (acertos / total) * 100
        print(f"Total de 'ENTRADAS' sugeridas: {total}")
        print(f"Acertos (Ganhou da Renda Fixa): {acertos}")
        print(f"Taxa de Acerto (Governança): {taxa:.1f}%")
        
        if taxa < 50:
            print("\n  ⚠️ ALERTA ESTATÍSTICO: O sistema falhou no teste histórico.")
            print("  Sugerindo redução de 10% no peso de 'Preço' para esse segmento.")
    else:
        print("Nenhuma entrada sugerida no período.")
    print("="*50 + "\n")
