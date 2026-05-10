import warnings
# Silenciamento absoluto no topo do arquivo
warnings.filterwarnings("ignore")

import time
from typing import List
from duckduckgo_search import DDGS

def buscar_noticias_fii(ticker: str) -> str:
    """
    Realiza busca simplificada que comprovadamente funciona.
    """
    query = f"{ticker} noticias"
    print(f"[web] Buscando notícias para {ticker}...")
    texto_consolidado = ""
    
    time.sleep(1) # Pausa para evitar bloqueio de bot
    
    try:
        with DDGS() as ddgs:
            # Usamos a aba de notícias (News) que é mais resiliente a bloqueios
            results = list(ddgs.news(query, max_results=8))
            print(f"[web] Encontrados {len(results)} resultados para {ticker}.")
            for r in results:
                # O motor de news usa 'body' para o resumo
                conteudo = r.get('body') or r.get('snippet') or ""
                texto_consolidado += f"Notícia ({r.get('date', '')}): {r.get('title')}\n{conteudo}\n\n"
    except Exception as e:
        print(f"[web] Erro na busca: {e}")
                
    return texto_consolidado
