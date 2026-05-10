import warnings
warnings.filterwarnings("ignore")
from duckduckgo_search import DDGS
import time

def test_search():
    print("Testando busca para MXRF11...")
    with DDGS() as ddgs:
        # Tenta uma busca mais genérica
        results = list(ddgs.text("MXRF11 noticias", max_results=5))
        print(f"Resultados encontrados: {len(results)}")
        for r in results:
            print(f"- {r['title']}")

if __name__ == "__main__":
    test_search()
