"""
coleta/api_fundamentus.py
Substitui o scraping do Status Invest usando scraping direto do fundamentus
para dados fundamentalistas mais estáveis (para FIIs).
"""
import re
from datetime import date
from typing import Optional, List
import requests
from bs4 import BeautifulSoup
from banco import db

def _limpar_valor(texto: str) -> Optional[float]:
    if not texto or texto == '-': return None
    t = texto.replace('.', '').replace(',', '.').replace('%', '').strip()
    try:
        return float(t)
    except ValueError:
        return None

def coletar_fii(ticker: str) -> Optional[dict]:
    """
    Coleta indicadores do FII fazendo parser direto no fundamentus.com.br.
    Retorna o dict com os dados padronizados.
    """
    ticker = ticker.upper().strip()
    hoje = date.today().isoformat()

    # Verifica se já coletou hoje
    existente = db.buscar_um(
        "SELECT * FROM indicadores WHERE ticker = ? AND data = ?",
        (ticker, hoje)
    )
    if existente:
        print(f"[fundamentus] {ticker} já coletado para {hoje}")
        return dict(existente)

    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        url = f"https://www.fundamentus.com.br/detalhes.php?papel={ticker}"
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        
        soup = BeautifulSoup(res.text, 'html.parser')
        tabelas = soup.find_all('table')
        if len(tabelas) < 3:
            print(f"[fundamentus] Nenhum dado encontrado para {ticker}.")
            return None
            
        dados_brutos = {}
        for tabela in tabelas:
            for row in tabela.find_all('tr'):
                cells = [c.text.strip().replace('?', '') for c in row.find_all(['th', 'td'])]
                # Pares chave-valor nas linhas (ex: [Chave1, Valor1, Chave2, Valor2...])
                for i in range(0, len(cells)-1, 2):
                    if cells[i]:
                        dados_brutos[cells[i]] = cells[i+1]
                        
    except Exception as e:
        print(f"[fundamentus] Erro ao buscar {ticker}: {e}")
        return None

    preco = _limpar_valor(dados_brutos.get("Cotação"))
    if not preco: # Tentar encoding falho
        preco = _limpar_valor(dados_brutos.get("Cotao"))
        
    vpa = _limpar_valor(dados_brutos.get("VP/Cota"))
    pvp = _limpar_valor(dados_brutos.get("P/VP"))
    dy_12m = _limpar_valor(dados_brutos.get("Div. Yield"))
    if dy_12m is not None:
        dy_12m = dy_12m / 100.0
        
    liquidez_fii = _limpar_valor(dados_brutos.get("Vol $ méd (2m)"))
    if not liquidez_fii:
        liquidez_fii = _limpar_valor(dados_brutos.get("Vol $ md (2m)"))
        
    patrimonio = _limpar_valor(dados_brutos.get("Patrim Líquido"))
    if not patrimonio:
        patrimonio = _limpar_valor(dados_brutos.get("Patrim Lquido"))
        
    vacancia = _limpar_valor(dados_brutos.get("Vacância Média"))
    if not vacancia:
        vacancia = _limpar_valor(dados_brutos.get("Vacncia Mdia"))
        
    qtd_ativos = _limpar_valor(dados_brutos.get("Qtd imóveis"))
    if not qtd_ativos:
        qtd_ativos = _limpar_valor(dados_brutos.get("Qtd imveis"))

    dados_finais = {
        "ticker":               ticker,
        "data":                 hoje,
        "preco":                preco,
        "pvp":                  pvp,
        "liquidez_diaria":      liquidez_fii,
        "ultimo_dividendo":     None,  # Pegaremos pelo yfinance
        "dy_3m":                None,
        "dy_6m":                None,
        "dy_12m":               dy_12m,
        "dy_patrimonial":       None,
        "vacancia_fisica":      vacancia,
        "vacancia_financeira":  None,
        "patrimonio_liquido":   patrimonio,
        "vpa":                  vpa,
        "qtd_ativos":           qtd_ativos,
        "fonte":                "fundamentus",
    }
    
    # Calcula confiabilidade
    confiabilidade = 100
    if preco is None: confiabilidade -= 20
    if pvp is None: confiabilidade -= 20
    if dy_12m is None: confiabilidade -= 20
    if liquidez_fii is None: confiabilidade -= 10
    
    dados_finais["confiabilidade"] = max(0, confiabilidade)

    tipo_fii = str(dados_brutos.get("Mandato", "INDEFINIDO"))
    segmento_fii = str(dados_brutos.get("Segmento", "INDEFINIDO"))
    db.inserir("fiis", {
        "ticker": ticker, 
        "nome": ticker, 
        "tipo": tipo_fii.upper(), 
        "segmento": segmento_fii.upper()
    })

    db.upsert("indicadores", dados_finais)

    print(
        f"[fundamentus] {ticker} coletado -> "
        f"Preço: R${preco} | "
        f"P/VP: {pvp} | "
        f"DY12M: {dy_12m} | "
        f"Confiabilidade: {dados_finais['confiabilidade']}%"
    )
    return dados_finais

def coletar_mercado_inteiro() -> List[dict]:
    """
    Raspa a tabela geral de FIIs do Fundamentus (Estágio 1 do Radar).
    Retorna uma lista de dicionários leves para pré-filtragem.
    """
    print("[radar] Varrendo o mercado inteiro no Fundamentus...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        url = "https://www.fundamentus.com.br/fii_resultado.php"
        res = requests.get(url, headers=headers, timeout=15)
        res.raise_for_status()
        
        soup = BeautifulSoup(res.text, 'html.parser')
        tabela = soup.find('table', {'id': 'tabelaResultado'})
        if not tabela:
            return []
            
        corpo = tabela.find('tbody')
        if not corpo:
            return []
            
        resultados = []
        for row in corpo.find_all('tr'):
            cols = [c.text.strip() for c in row.find_all('td')]
            if len(cols) < 13: continue
            
            ticker = cols[0].upper()
            
            # Mapeamento leve para pré-filtro
            d = {
                "ticker":           ticker,
                "segmento":         cols[1].upper(),
                "preco":            _limpar_valor(cols[2]),
                "dy_12m":           _limpar_valor(cols[4]) / 100.0 if _limpar_valor(cols[4]) else 0,
                "pvp":              _limpar_valor(cols[5]),
                "liquidez":         _limpar_valor(cols[7]),
                "qtd_ativos":       _limpar_valor(cols[8]),
                "vacancia_media":   _limpar_valor(cols[12])
            }
            resultados.append(d)
            
        print(f"[radar] {len(resultados)} FIIs encontrados para análise.")
        return resultados
    except Exception as e:
        print(f"[radar] Erro ao varrer mercado: {e}")
        return []

