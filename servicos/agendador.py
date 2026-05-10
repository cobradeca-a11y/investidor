"""
servicos/agendador.py
Gerencia as rotinas automáticas do FIIA (O Funcionário Digital).
"""
import schedule
import time
import threading
from datetime import datetime
from processamento import estrategia
from coleta import api_bcb, api_fundamentus, api_yfinance

def rotina_diaria_abertura():
    """Executada às 09:00 - Prepara os dados para o dia."""
    print(f"[{datetime.now()}] Iniciando Rotina de Abertura...")
    api_bcb.coletar_macro()
    print("[agendador] Dados macroeconômicos atualizados.")

def rotina_oportunidades_mercado():
    """Executada às 11:00 - Busca peixe grande com a bolsa aberta."""
    print(f"[{datetime.now()}] Iniciando Radar de Oportunidades...")
    # Executa apenas a parte técnica para ser rápido
    estrategia.radar_oportunidades()
    print("[agendador] Radar de oportunidades concluído e salvo no banco.")

def rotina_semanal_deep_scan():
    """Executada aos Sábados - Rede de Arrastão completa (IA)."""
    print(f"[{datetime.now()}] Iniciando Grande Rede de Arrastão (IA)...")
    vencedores = estrategia.radar_oportunidades()
    print(f"[agendador] Deep Scan concluído para {len(vencedores)} fundos.")

def rotina_noturna_cvm():
    """Executada às 20:00 - Captura fatos relevantes e notícias pós-fechamento."""
    print(f"[{datetime.now()}] Iniciando Varredura Noturna (CVM/RI)...")
    estrategia.radar_oportunidades() # IA analisa o que saiu no fim do dia
    print("[agendador] Dossiê noturno concluído.")

# Agendamento Estratégico (Baseado nas Horas de Ouro da B3)
schedule.every().day.at("09:00").do(rotina_diaria_abertura)        # O Plano
schedule.every().day.at("10:45").do(rotina_oportunidades_mercado) # A Primeira Leitura Limpa
schedule.every().day.at("20:00").do(rotina_noturna_cvm)           # O Dossiê CVM Noturno
schedule.every().saturday.at("10:00").do(rotina_semanal_deep_scan)# Análise Profunda


def iniciar_agendador_background():
    """Inicia o loop do agendador em uma thread separada."""
    def loop():
        while True:
            schedule.run_pending()
            time.sleep(60)
            
    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    print("[agendador] Motor de rotinas ligado em segundo plano.")

if __name__ == "__main__":
    print("Iniciando Agendador FIIA Standalone...")
    rotina_diaria_abertura() # Roda uma vez ao ligar para garantir dados
    while True:
        schedule.run_pending()
        time.sleep(1)
