import sys
import os
# Garante que o Python use UTF-8 no stdout
sys.stdout.reconfigure(encoding='utf-8')

import main
from processamento.analise_qualitativa import analisar_fundo_ia

def analise_completa(ticker):
    print(f"\n{'='*50}")
    print(f"      FIIA DEEP ANALYSIS - {ticker}")
    print(f"{'='*50}")
    
    # Parte 1: Matemática (Preço Justo e Filtros)
    main.analisar_fii(ticker)
    
    # Parte 2: IA (Notícias e Sentimento)
    print("\n🔍 ACIONANDO CÉREBRO QUALITATIVO...")
    qual = analisar_fundo_ia(ticker)
    
    print("\n" + "—"*50)
    print(f"🏆 VEREDITO QUALITATIVO (Score: {qual.get('score')}/10)")
    print(f"📝 RESUMO: {qual.get('resumo')}")
    print("⚠️ RISCOS DETECTADOSpp:")
    for r in qual.get("riscos", []):
        print(f"  • {r}")
    print("—"*50)

if __name__ == "__main__":
    analise_completa("MXRF11")
