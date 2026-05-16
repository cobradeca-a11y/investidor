"""
servicos/agendador.py
Gerencia as rotinas automáticas do FIIA (O Funcionário Digital).
"""
import schedule
import time
import threading
from datetime import datetime
from processamento import estrategia
from coleta import api_bcb, cvm_informe_mensal, informe_diario, informe_trimestral
from servicos.agendador_avaliador import executar_avaliador_temporal


def rotina_diaria_abertura():
    """Executada às 09:00 - Prepara os dados para o dia."""
    print(f"[{datetime.now()}] Iniciando Rotina de Abertura...")
    api_bcb.coletar_macro()
    print("[agendador] Dados macroeconômicos atualizados.")


def rotina_avaliador_temporal():
    """Executada diariamente - Avalia decisões vencidas em 90d/365d."""
    print(f"[{datetime.now()}] Iniciando Avaliador Temporal...")
    resultado = executar_avaliador_temporal()
    print(f"[agendador] Avaliador temporal concluído: {resultado}")


def rotina_cvm_diaria():
    """Executada diariamente - Atualiza o informe diário CVM do mês corrente."""
    print(f"[{datetime.now()}] Iniciando Coleta CVM Diária...")
    registros = informe_diario.coletar_mes_atual()
    print(f"[agendador] Informe diário CVM atualizado: {registros} registros.")


def rotina_cvm_mensal():
    """Executada mensalmente - Atualiza informes mensais CVM do ano corrente."""
    print(f"[{datetime.now()}] Iniciando Coleta CVM Mensal...")
    resultado = cvm_informe_mensal.coletar_ano(datetime.now().year)
    print(f"[agendador] Informe mensal CVM atualizado: {resultado}")


def rotina_cvm_trimestral():
    """Executada semanalmente - Mantém o último informe trimestral CVM sincronizado."""
    print(f"[{datetime.now()}] Iniciando Coleta CVM Trimestral...")
    resultado = informe_trimestral.coletar_atual()
    print(f"[agendador] Informe trimestral CVM atualizado: {resultado}")


def rotina_oportunidades_mercado():
    """Executada às 11:00 - Busca oportunidades com a bolsa aberta."""
    print(f"[{datetime.now()}] Iniciando Radar de Oportunidades...")
    estrategia.radar_oportunidades()
    print("[agendador] Radar de oportunidades concluído e salvo no banco.")


def rotina_semanal_deep_scan():
    """Executada aos Sábados - Análise profunda."""
    print(f"[{datetime.now()}] Iniciando Grande Rede de Arrastão (IA)...")
    vencedores = estrategia.radar_oportunidades()
    print(f"[agendador] Deep Scan concluído para {len(vencedores)} fundos.")


def rotina_noturna_radar():
    """Executada às 20:00 - Varredura noturna do radar."""
    print(f"[{datetime.now()}] Iniciando Varredura Noturna do Radar...")
    estrategia.radar_oportunidades()
    print("[agendador] Dossiê noturno do radar concluído.")


# Agendamento Estratégico
schedule.every().day.at("06:00").do(rotina_avaliador_temporal)     # Aprendizado operacional
schedule.every().day.at("07:00").do(rotina_cvm_diaria)             # CVM diário
schedule.every().monday.at("07:20").do(rotina_cvm_trimestral)      # CVM trimestral
schedule.every().day.at("09:00").do(rotina_diaria_abertura)        # Macro
schedule.every().day.at("10:45").do(rotina_oportunidades_mercado) # Radar
schedule.every().day.at("20:00").do(rotina_noturna_radar)         # Dossiê noturno do radar
schedule.every().day.at("22:30").do(lambda: rotina_cvm_mensal() if datetime.now().day == 1 else None)
schedule.every().saturday.at("10:00").do(rotina_semanal_deep_scan)# Deep scan


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
    rotina_diaria_abertura()
    rotina_avaliador_temporal()
    while True:
        schedule.run_pending()
        time.sleep(1)
