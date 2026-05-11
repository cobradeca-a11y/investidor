import sys
import os

# Adiciona o diretório atual ao path para garantir que os pacotes sejam encontrados
sys.path.append(os.getcwd())

try:
    from processamento import estrategia
    print("[diag] Import de estrategia OK")
    
    # Tenta rodar uma parte do radar para ver onde quebra
    # Vamos testar apenas os imports internos de radar_oportunidades primeiro
    from coleta.api_fundamentus import coletar_mercado_inteiro
    from decisao.motor_decisao import decidir
    from decisao.persistencia_decisao import gravar
    print("[diag] Imports internos de radar_oportunidades OK")
    
    # Executa o radar
    print("[diag] Executando estrategia.radar_oportunidades()...")
    vencedores = estrategia.radar_oportunidades()
    print(f"[diag] Sucesso! {len(vencedores)} oportunidades encontradas.")

except Exception as e:
    import traceback
    print("[diag] ERRO DETECTADO:")
    traceback.print_exc()
