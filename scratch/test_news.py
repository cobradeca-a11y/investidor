import warnings
warnings.filterwarnings("ignore")
from duckduckgo_search import DDGS
import time

def test_news_search():
    print("Testando busca de NOTÍCIAS (News) para MXRF11...")
    try:
        with DDGS() as ddgs:
            # Em vez de .text, usamos .news
            results = list(ddgs.news("MXRF11", max_results=5))
            print(f"Resultados de Notícias encontrados: {len(results)}")
            for r in results:
                print(f"- {r['title']} ({r['date']})")
    except Exception as e:
        print(f"Erro no motor de notícias: {e}")

if __name__ == "__main__":
    test_news_search()
