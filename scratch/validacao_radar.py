
import sys
import os
# Adiciona o diretório atual ao path para importar os módulos do projeto
sys.path.append(os.getcwd())

from processamento.estrategia import radar_oportunidades
import json

print("\n--- INICIANDO VALIDAÇÃO PROFISSIONAL DO FIIA v2.1 ---")
try:
    # Executa o radar completo (os logs aparecerão no terminal)
    finalistas = radar_oportunidades()
    
    print("\n--- RELATÓRIO DE FINALISTAS ---")
    for f in finalistas:
        v = f["veredito"]
        print(f"ATIVO: {v['ticker']} | DECISÃO: {v['decisao']} | MARGEM: {v['margem']}% | CONFIANÇA: {v['confianca']}")
        print(f"TRILHA: {' -> '.join(v['trilha_gates'])}")
        print("-" * 30)

except Exception as e:
    print(f"\n[ERRO CRÍTICO NA VALIDAÇÃO]: {e}")
    import traceback
    traceback.print_exc()
