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
from coleta.informe_anual import coletar_atual as anual_atual
from coleta.informe_trimestral_completo import coletar_atual as tri_completo_atual
from servicos.agendador_avaliador import executar_avaliador_temporal
from servicos.assistente_financeiro import gerar_alertas, gravar_alertas_gatilhos
from aprendizado.snapshots import criar_snapshots_diarios
from aprendizado.paper_trading import executar_paper_trading_diario
from operacional.saude_fontes import gerar_relatorio_saude_fontes
from carteira.repositorio_carteira import listar_posicoes
from decisao import gatilhos as mod_gatilhos
from coleta.contexto_ativo import obter_contexto_ativo
from sistema import observabilidade


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


def rotina_cvm_trimestral_completa():
    """Executada semanalmente - Persiste tabelas trimestrais estendidas."""
    print(f"[{datetime.now()}] Iniciando Coleta CVM Trimestral Completa...")
    resultado = tri_completo_atual()
    print(f"[agendador] Informe trimestral completo atualizado: {resultado}")


def rotina_cvm_anual():
    """Executada anualmente - Atualiza informes anuais completos."""
    print(f"[{datetime.now()}] Iniciando Coleta CVM Anual...")
    resultado = anual_atual()
    print(f"[agendador] Informe anual CVM atualizado: {resultado}")


def rotina_snapshots_diarios():
    print(f"[{datetime.now()}] Iniciando Snapshots Diários...")
    resultado = criar_snapshots_diarios()
    print(f"[agendador] Snapshots concluídos: {resultado}")


def rotina_paper_trading_diario():
    print(f"[{datetime.now()}] Iniciando Paper Trading Diário...")
    resultado = executar_paper_trading_diario()
    print(f"[agendador] Paper trading concluído: {resultado.get('resumo')}")


def rotina_saude_fontes():
    print(f"[{datetime.now()}] Iniciando Saúde das Fontes...")
    resultado = gerar_relatorio_saude_fontes()
    print(f"[agendador] Saúde das fontes concluída: {resultado.get('cobertura')}")


def rotina_alertas_assistente():
    """Executada diariamente - Persiste alertas operacionais para a PWA."""
    print(f"[{datetime.now()}] Iniciando Alertas do Assistente...")
    resultado = gerar_alertas()
    print(f"[agendador] Alertas do assistente concluidos: {resultado.get('quantidade', 0)} alerta(s).")


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


def rotina_gatilhos_carteira():
    """
    Executada diariamente - Verifica gatilhos de gestão de posição
    para todos os ativos em carteira e registra alertas operacionais.

    Fontes de dados por campo:
      pvp, vacancia_fisica, dy_recorrente → contexto ativo (coleta ao vivo)
      margem, score_ia                    → última decisão gravada no banco
    """
    from banco import db as _db

    print(f"[{datetime.now()}] Iniciando Verificação de Gatilhos da Carteira...")
    posicoes = listar_posicoes()

    if not posicoes:
        print("[agendador] Nenhuma posição em carteira. Gatilhos ignorados.")
        return

    alertas_acionados = []

    for pos in posicoes:
        ticker = pos.get("ticker")
        if not ticker:
            continue

        try:
            contexto = obter_contexto_ativo(ticker)
            pvp           = contexto.get("pvp")
            vacancia      = contexto.get("vacancia_fisica")
            dy_recorrente = contexto.get("dy_recorrente")

            # margem e score_ia vêm da última decisão gravada
            ultima_decisao = _db.buscar_um(
                """
                SELECT margem, score_ia FROM decisoes
                WHERE ticker = ?
                ORDER BY data_decisao DESC LIMIT 1
                """,
                (ticker,),
            )
            margem   = ultima_decisao.get("margem")   if ultima_decisao else None
            score_ia = ultima_decisao.get("score_ia") if ultima_decisao else None

            resultado = mod_gatilhos.verificar(
                ticker=ticker,
                pvp=pvp,
                vacancia=vacancia,
                margem=margem,
                score_ia=score_ia,
                dy_recorrente_atual=dy_recorrente,
            )

            if resultado["total_gatilhos"] > 0:
                alertas_acionados.append(resultado)
                observabilidade.registrar_evento(
                    "WARN",
                    "servicos.agendador.gatilhos",
                    f"Gatilho acionado: {ticker} → {resultado['acao_principal']}",
                    contexto={
                        "ticker": ticker,
                        "acao": resultado["acao_principal"],
                        "gatilhos": resultado["gatilhos"],
                    },
                )
                print(
                    f"  [gatilho] {ticker}: {resultado['acao_principal']} "
                    f"({resultado['total_gatilhos']} gatilho(s))"
                )
            else:
                print(f"  [gatilho] {ticker}: MANTER — nenhum gatilho acionado.")

        except Exception as erro:
            observabilidade.registrar_erro(
                "servicos.agendador.gatilhos",
                erro,
                contexto={"ticker": ticker},
            )
            print(f"  [gatilho] ERRO ao verificar {ticker}: {erro}")

    if alertas_acionados:
        resultado_gravacao = gravar_alertas_gatilhos(alertas_acionados)
        print(f"[agendador] Alertas de gatilho gravados no assistente: {resultado_gravacao.get('gravados', 0)}")

    print(
        f"[agendador] Verificação de gatilhos concluída: "
        f"{len(alertas_acionados)} ativo(s) com alerta de {len(posicoes)} em carteira."
    )


def rotina_noturna_radar():
    """Executada às 20:00 - Varredura noturna do radar."""
    print(f"[{datetime.now()}] Iniciando Varredura Noturna do Radar...")
    estrategia.radar_oportunidades()
    print("[agendador] Dossiê noturno do radar concluído.")


# Agendamento Estratégico
schedule.every().day.at("06:00").do(rotina_avaliador_temporal)
schedule.every().day.at("07:00").do(rotina_cvm_diaria)
schedule.every().monday.at("07:20").do(rotina_cvm_trimestral)
schedule.every().monday.at("07:35").do(rotina_cvm_trimestral_completa)
schedule.every().day.at("08:00").do(rotina_snapshots_diarios)
schedule.every().day.at("08:30").do(rotina_alertas_assistente)
schedule.every().day.at("09:00").do(rotina_diaria_abertura)
schedule.every().day.at("10:00").do(rotina_paper_trading_diario)
schedule.every().day.at("10:45").do(rotina_oportunidades_mercado)
schedule.every().day.at("11:15").do(rotina_gatilhos_carteira)
schedule.every().day.at("11:30").do(rotina_alertas_assistente)
schedule.every().day.at("20:00").do(rotina_noturna_radar)
schedule.every().day.at("22:30").do(lambda: rotina_cvm_mensal() if datetime.now().day == 1 else None)
schedule.every().day.at("22:45").do(lambda: rotina_cvm_anual() if datetime.now().month in [3, 4] and datetime.now().day == 1 else None)
schedule.every().day.at("23:00").do(rotina_saude_fontes)
schedule.every().saturday.at("10:00").do(rotina_semanal_deep_scan)


_agendador_iniciado = False
_lock = threading.Lock()


def iniciar_agendador_background():
    """Inicia o loop do agendador em uma thread separada com protecao contra multiplas inicializacoes."""
    global _agendador_iniciado
    with _lock:
        if _agendador_iniciado:
            print("[agendador] Tentativa de iniciar agendador ja ativo ignorada.")
            return
        _agendador_iniciado = True

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
