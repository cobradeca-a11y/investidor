"""
main.py
Ponto de entrada do sistema FIIA.
"""
import sys
import argparse
from pathlib import Path
from banco import db
from acesso import auth
from coleta import api_bcb, api_fundamentus, api_yfinance
from processamento import estrategia, tradutor
from backtest import maquina_tempo
from sistema import autoupdater

def setup():
    """Inicializa o banco de dados."""
    print("Iniciando setup do banco de dados...")
    db.inicializar()
    print("Setup concluído com sucesso.")

def analisar_fii(ticker: str):
    """Executa a coleta e análise completa de um FII específico."""
    print(f"\n{'='*50}\n  ANALISANDO: {ticker}\n{'='*50}")
    print(f"\nColetando dados do FII: {ticker} (Fundamentus)...")
    dados_fii = api_fundamentus.coletar_fii(ticker)
    
    print(f"\nColetando histórico e dividendos: {ticker} (Yahoo Finance)...")
    api_yfinance.coletar_historico_dividendos(ticker)
    
    if dados_fii:
        print("\n--- RESUMO COLETADO ---")
        print(f"Ticker: {dados_fii.get('ticker')}")
        print(f"Preço Atual: R$ {dados_fii.get('preco')}")
        print(f"P/VP: {dados_fii.get('pvp')}")
        print(f"VPA (Valor Patrimonial): R$ {dados_fii.get('vpa')}")
        print(f"DY 12M: {dados_fii.get('dy_12m')}")
        print(f"Confiabilidade: {dados_fii.get('confiabilidade')}%")
        
        # --- Camada 1: Filtros de Sobrevivência ---
        print("\n--- CAMADA 1: FILTROS DE SOBREVIVÊNCIA ---")
        aprovado, motivos = estrategia.aplicar_filtros_sobrevivencia(ticker)
        print(tradutor.explicar_sobrevivencia(aprovado, motivos))
        
        if aprovado:
            # --- Camada 2 e 3: Motor Quantitativo e Macro ---
            from processamento.margem_seguranca import relatorio_margem
            print("\n--- CAMADA 2 e 3: AVALIAÇÃO DE PREÇO E RISCO MACRO ---")
            rel_margem = relatorio_margem(ticker)
            if rel_margem.get("calculavel"):
                print(f"Preço Atual: R$ {rel_margem['preco_atual']:.2f}")
                print(f"Preço Justo: R$ {rel_margem['preco_justo']:.2f}")
                print(f"Piso de Segurança (Stress Test): R$ {rel_margem['preco_stress']:.2f}")
                margem_pct = rel_margem['margem_percentual'] * 100
                sinal = "+" if margem_pct > 0 else ""
                print(f"Margem de Segurança: {sinal}{margem_pct:.1f}%")
                print(f"Veredito de Preço: {rel_margem['avaliacao']}")
                
                print("\n" + tradutor.explicar_valuation(
                    segmento=rel_margem['segmento'],
                    preco_atual=rel_margem['preco_atual'],
                    preco_justo=rel_margem['preco_justo'],
                    preco_stress=rel_margem['preco_stress'],
                    avaliacao=rel_margem['avaliacao'],
                    dy_anual=rel_margem.get('dy_anual'),
                    taxa_desconto=rel_margem.get('taxa_desconto', 0)
                ))

def demonstracao():
    """Demonstração padrão para 1 FII."""
    autoupdater.verificar_e_atualizar()
    print("\nColetando dados macroeconômicos...")
    api_bcb.coletar_macro()
    analisar_fii("HGLG11")

def rodar_top10():
    """Analisa os 10 FIIs mais populares do mercado."""
    autoupdater.verificar_e_atualizar()
    print("\nColetando dados macroeconômicos...")
    api_bcb.coletar_macro()
    
    lista = ["HGLG11", "MXRF11", "KNCR11", "BTLG11", "VISC11", "XPML11", "CPTS11", "XPLG11", "IRDM11", "VILG11"]
    for t in lista:
        analisar_fii(t)

def rodar_radar():
    """Busca e exibe apenas as melhores oportunidades do mercado inteiro."""
    autoupdater.verificar_e_atualizar()
    print("\nColetando dados macroeconômicos...")
    api_bcb.coletar_macro()
    
    # Aciona o motor de busca (Top 15 com IA)
    oportunidades = estrategia.radar_oportunidades()
    
    print("\n" + "="*50)
    print("      O PODIUM DO RADAR FIIA (TOP 15)")
    print("="*50)
    
    if not oportunidades:
        print("\n[radar] O mercado está caro! Nenhuma oportunidade com margem de segurança positiva encontrada.")
        return
        
    for i, op in enumerate(oportunidades):
        print(f"\n🏆 {i+1}º LUGAR: {op['ticker']} (Margem: {op['margem']:.1f}%)")
        
        # Só exibe o relatório completo para os Top 3 para não inundar a tela
        if i < 3:
            analisar_fii(op['ticker'])
            # Exibe a análise qualitativa se disponível
            qual = op.get("qualitativo")
            if qual:
                print(f"\n🔍 INVESTIGAÇÃO QUALITATIVA (Score: {qual.get('score', '?')}/10)")
                print(f"Resumo: {qual.get('resumo', 'N/A')}")
                print("Riscos Detectados:")
                for r in qual.get("riscos", []):
                    print(f"  • {r}")
        else:
            print(f"   -> Análise técnica e qualitativa disponível no modo detalhado.")
            
        print("-" * 50)


def rodar_backtest(ticker: str):
    """Aciona a máquina do tempo para o FII especificado."""
    # Chama o auto-updater
    autoupdater.verificar_e_atualizar()
    
    # É preciso puxar o histórico de dividendos para rodar
    api_yfinance.coletar_historico_dividendos(ticker)
    
    from backtest.maquina_tempo import executar_backtest
    executar_backtest(ticker)

def main():
    parser = argparse.ArgumentParser(description="FIIA - Fundo Inteligente de Investimento em Ativos")
    parser.add_argument("--setup", action="store_true", help="Inicializa o banco de dados e as tabelas.")
    parser.add_argument("--backtest", type=str, help="Roda a máquina do tempo simulando 5 anos no passado para o TICKER.")
    parser.add_argument("--top10", action="store_true", help="Analisa os 10 FIIs mais populares do mercado.")
    parser.add_argument("--radar", action="store_true", help="Varre o mercado inteiro em busca de oportunidades reais.")
    
    args = parser.parse_args()

    if args.setup:
        setup()
    elif args.backtest:
        auth.exigir_autenticacao()
        rodar_backtest(args.backtest.upper())
    elif args.top10:
        auth.exigir_autenticacao()
        rodar_top10()
    elif args.radar:
        auth.exigir_autenticacao()
        rodar_radar()
    else:
        # Pede senha para a demonstração normal
        auth.exigir_autenticacao()
        demonstracao()

if __name__ == "__main__":
    main()
