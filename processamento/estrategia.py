"""
processamento/estrategia.py
Módulo responsável pelas camadas de avaliação qualitativa e filtros de sobrevivência.
"""
from typing import Tuple, List
from banco import db

def aplicar_filtros_sobrevivencia(ticker: str) -> Tuple[bool, List[str]]:
    """
    Camada 1: Filtros de Sobrevivência (Corte Rápido)
    Retorna (Aprovado, [Lista de motivos de reprovação]).
    """
    ind_row = db.buscar_um(
        "SELECT * FROM indicadores WHERE ticker = ? ORDER BY data DESC LIMIT 1",
        (ticker,)
    )
    
    fii_info_row = db.buscar_um("SELECT * FROM fiis WHERE ticker = ?", (ticker,))
    
    if not ind_row or not fii_info_row:
        return False, ["Dados insuficientes no banco para avaliação."]
        
    ind = dict(ind_row)
    fii_info = dict(fii_info_row)
        
    motivos_reprovacao = []
    
    # 1. Filtro de Liquidez Diária (Mínimo R$ 1 Milhão)
    liquidez = ind.get("liquidez_diaria")
    if liquidez is None or liquidez < 1000000:
        val = f"R${liquidez:,.2f}" if liquidez else "Desconhecida"
        motivos_reprovacao.append(f"Liquidez baixa ({val}). Risco de não conseguir vender as cotas.")
        
    # 2. Filtro de Vacância Física (Máximo 15%)
    # Apenas para FIIs que não são de Papel
    segmento = fii_info.get("segmento", "").upper()
    if "PAPEL" not in segmento and "RECEBÍVEIS" not in segmento:
        vacancia = ind.get("vacancia_fisica")
        if vacancia is not None and vacancia > 15.0:
            motivos_reprovacao.append(f"Vacância alta ({vacancia}%). Muitos imóveis vazios.")
            
    # 3. Filtro de Diversificação (Mínimo 5 imóveis)
    # Apenas para tijolo
    if "PAPEL" not in segmento and "RECEBÍVEIS" not in segmento:
        qtd_ativos = ind.get("qtd_ativos")
        if qtd_ativos is not None and qtd_ativos < 5:
            motivos_reprovacao.append(f"Baixa diversificação ({int(qtd_ativos)} imóveis). Risco concentrado.")
            
    aprovado = len(motivos_reprovacao) == 0
    return aprovado, motivos_reprovacao

def radar_oportunidades():
    """
    Implementa o Funil de 2 Estágios:
    1. Pré-filtro massivo por Liquidez, Vacância e Ativos.
    2. Deep Scan dos sobreviventes para calcular Margem Real.
    """
    from coleta.api_fundamentus import coletar_mercado_inteiro
    from processamento.margem_seguranca import calcular_margem_seguranca
    from processamento.analise_qualitativa import analisar_fundo_ia
    from coleta import api_fundamentus, api_yfinance
    
    # Estágio 1: Varredura de Mercado
    mercado = coletar_mercado_inteiro()
    elite = []
    
    print("[radar] Aplicando filtros de sobrevivência iniciais...")
    for fii in mercado:
        ticker = fii["ticker"]
        segmento = fii["segmento"]
        
        # Filtros rápidos (Camada 1 simplificada)
        if fii["liquidez"] < 1000000: continue
        
        if "PAPEL" not in segmento and "RECEBÍVEIS" not in segmento:
            if fii["vacancia_media"] > 15.0: continue
            if fii["qtd_ativos"] < 5: continue
            
        elite.append(ticker)
        
    print(f"[radar] {len(elite)} FIIs passaram para o Raio-X profundo.")
    
    # Estágio 2: Deep Scan
    oportunidades = []
    
    # Processamos a elite para encontrar as melhores margens de segurança (limitado a 50)
    for ticker in elite[:50]:
        print(f"[radar] Analisando {ticker}...", end="\r")
        api_fundamentus.coletar_fii(ticker)
        api_yfinance.coletar_historico_dividendos(ticker)
        
        margem = calcular_margem_seguranca(ticker)
        if margem and margem > 0:
            oportunidades.append({
                "ticker": ticker,
                "margem": margem
            })
            
    # Ordena pelas melhores oportunidades
    oportunidades.sort(key=lambda x: x["margem"], reverse=True)
    
    # MODO TESTE: Apenas o #1 para ajuste fino da IA
    vencedores = oportunidades[:1]
    for fii in vencedores:
        print(f"[radar] Investigando {fii['ticker']} na internet...")
        fii["qualitativo"] = analisar_fundo_ia(fii["ticker"])
        # Pausa de 4 segundos para respeitar o limite grátis da API (15 RPM)
        import time
        time.sleep(4)
        
    return vencedores


