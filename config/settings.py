"""
config/settings.py
Configurações do perfil de investimento e limites do sistema.
Edite aqui para ajustar parâmetros sem mexer na lógica.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────
# Perfil do investidor
# ─────────────────────────────────────────
OBJETIVO = "RENDA_PASSIVA"          # RENDA_PASSIVA | CRESCIMENTO | MISTO
HORIZONTE = "LONGO_PRAZO"           # CURTO | MEDIO | LONGO_PRAZO

# ─────────────────────────────────────────
# Limites da carteira
# ─────────────────────────────────────────
CONCENTRACAO_MAX_POR_ATIVO = 0.10       # 10% da carteira por ativo
CONCENTRACAO_MAX_POR_SEGMENTO = 0.30    # 30% por segmento
CONCENTRACAO_MAX_POR_TIPO = 0.50        # 50% por tipo (papel, tijolo, etc)
CONCENTRACAO_MAX_POR_GESTORA = 0.25     # 25% por gestora

# ─────────────────────────────────────────
# Exigências mínimas para entrada
# ─────────────────────────────────────────
PREMIO_CDI_MINIMO = 1.5             # pontos percentuais acima do CDI
LIQUIDEZ_MINIMA_DIARIA = 50_000     # R$ 50.000 de liquidez mínima
CONFIABILIDADE_MINIMA = 60          # score mínimo de dados (0-100)
HISTORICO_MINIMO_MESES = 24         # meses de histórico mínimo
PERCENTUAL_RECORRENTE_MINIMO = 0.70 # 70% do DY deve ser recorrente

# ─────────────────────────────────────────
# Faixas de classificação do score
# ─────────────────────────────────────────
SCORE_ATIVO_FORTE = 75
SCORE_ATIVO_BOM = 60
SCORE_ATIVO_MEDIO = 45
SCORE_ATIVO_FRACO = 30
# abaixo de 30 = PROBLEMÁTICO

# ─────────────────────────────────────────
# Pesos estáticos iniciais por segmento
# NÃO calibrar automaticamente antes da amostra mínima.
# PAPEL/CRI não penaliza estruturalmente P/VP.
# ─────────────────────────────────────────
PESOS_SCORE_SEGMENTADO = {
    "DEFAULT": {
        "dy_recorrente": 20,
        "premio_cdi": 15,
        "confiabilidade": 15,
        "historico": 10,
        "pvp": 15,
        "vacancia": 10,
        "liquidez": 5,
        "score_cvm": 10,
    },
    "PAPEL": {
        "dy_recorrente": 30,
        "premio_cdi": 30,
        "confiabilidade": 15,
        "historico": 10,
        "liquidez": 5,
        "score_cvm": 10,
    },
    "LOGISTICA": {
        "dy_recorrente": 15,
        "premio_cdi": 10,
        "confiabilidade": 15,
        "historico": 10,
        "pvp": 20,
        "vacancia": 15,
        "liquidez": 5,
        "score_cvm": 10,
    },
    "LAJES": {
        "dy_recorrente": 10,
        "premio_cdi": 10,
        "confiabilidade": 15,
        "historico": 10,
        "pvp": 20,
        "vacancia": 20,
        "liquidez": 5,
        "score_cvm": 10,
    },
    "SHOPPINGS": {
        "dy_recorrente": 15,
        "premio_cdi": 10,
        "confiabilidade": 15,
        "historico": 10,
        "pvp": 15,
        "vacancia": 15,
        "liquidez": 5,
        "score_cvm": 15,
    },
    "HIBRIDO": {
        "dy_recorrente": 15,
        "premio_cdi": 15,
        "confiabilidade": 15,
        "historico": 10,
        "pvp": 15,
        "vacancia": 10,
        "liquidez": 5,
        "score_cvm": 15,
    },
}

# ─────────────────────────────────────────
# Janelas de avaliação do paper trading
# 180 dias removido até existir suporte completo no avaliador.
# ─────────────────────────────────────────
JANELAS_AVALIACAO_DIAS = [90, 365]

# ─────────────────────────────────────────
# Governança do aprendizado adaptativo
# ─────────────────────────────────────────
APRENDIZADO_AMOSTRAS_MINIMAS = 50
APRENDIZADO_DIFERENCA_CDI_MINIMA = 8.0     # % abaixo do CDI para considerar erro
APRENDIZADO_SEGMENTOS_MINIMOS = 3          # consistência entre segmentos

# ─────────────────────────────────────────
# URLs das fontes de dados
# ─────────────────────────────────────────
URL_STATUS_INVEST = "https://statusinvest.com.br/fundos-imobiliarios/{ticker}"
URL_FUNDS_EXPLORER = "https://www.fundsexplorer.com.br/funds/{ticker}"
URL_B3_FIIS = "https://www.b3.com.br/pt_br/produtos-e-servicos/negociacao/renda-variavel/fundos-de-investimentos/fii/fiis-listados/"

URL_BCB_SELIC = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.11/dados/ultimos/1?formato=json"
URL_BCB_CDI   = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados/ultimos/1?formato=json"
URL_BCB_IPCA  = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados/ultimos/1?formato=json"

# ─────────────────────────────────────────
# Versão atual do modelo
# ─────────────────────────────────────────
VERSAO_MODELO = "1.0"

# ─────────────────────────────────────────
# Chaves de API (Configuração do Cérebro)
# ─────────────────────────────────────────
# Defina GEMINI_API_KEY no arquivo .env na raiz do projeto:
#   GEMINI_API_KEY=sua_chave_aqui
# Obtenha sua chave em: https://aistudio.google.com/app/apikey
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

if not GEMINI_API_KEY:
    import warnings
    warnings.warn(
        "GEMINI_API_KEY não encontrada. Crie um arquivo .env na raiz com GEMINI_API_KEY=sua_chave.",
        stacklevel=2,
    )
