"""
sistema/autoupdater.py
Verifica se as bibliotecas críticas (fundamentus e yfinance) estão desatualizadas
no pip e força uma atualização para garantir estabilidade da coleta.
"""
import subprocess
import json
import sys

# Bibliotecas que mudam com frequência e afetam a coleta
LIBS_CRITICAS = ["yfinance", "fundamentus"]

def _executar_pip_list_outdated() -> list[dict]:
    try:
        resultado = subprocess.run(
            [sys.executable, "-m", "pip", "list", "--outdated", "--format=json"],
            capture_output=True,
            text=True,
            check=True
        )
        return json.loads(resultado.stdout)
    except Exception as e:
        print(f"[autoupdater] Aviso: Falha ao checar pacotes desatualizados via pip: {e}")
        return []

def _atualizar_pacotes(pacotes: list[str]) -> bool:
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade"] + pacotes,
            capture_output=True,
            text=True,
            check=True
        )
        return True
    except Exception as e:
        print(f"[autoupdater] Erro ao atualizar {pacotes}: {e}")
        return False

def verificar_e_atualizar() -> None:
    """Verifica bibliotecas críticas e atualiza silenciosamente."""
    # Como rodar pip list outdated pode demorar alguns segundos,
    # pode ser interessante rodar isso apenas em certas condições, 
    # mas para esse escopo faremos a verificação a cada execução de forma transparente.
    
    outdated = _executar_pip_list_outdated()
    
    pacotes_para_atualizar = []
    relatorios = []
    
    for lib in outdated:
        nome = lib.get("name", "")
        if nome in LIBS_CRITICAS:
            versao_atual = lib.get("version", "desconhecida")
            versao_nova = lib.get("latest_version", "desconhecida")
            pacotes_para_atualizar.append(nome)
            relatorios.append(f"• {nome}: v{versao_atual} → v{versao_nova}")

    if pacotes_para_atualizar:
        print(f"\n[autoupdater] Atualização de bibliotecas de mercado detectada.")
        print(f"Baixando versões mais recentes para evitar quebras de coleta...")
        sucesso = _atualizar_pacotes(pacotes_para_atualizar)
        
        print("-" * 50)
        print("  RELATÓRIO DE MANUTENÇÃO (Auto-Updater)")
        print("-" * 50)
        if sucesso:
            print("As seguintes bibliotecas críticas foram atualizadas com sucesso:")
            for r in relatorios:
                print(f"  {r}")
            print("Isso garante que o scraping de dados financeiros continue estável.")
        else:
            print("Falha ao tentar atualizar as bibliotecas.")
        print("-" * 50 + "\n")
