"""
Teste 8.2 — Disparar a rotina completa do agendador.
Roda sem servidor. Lê dados reais do banco e contexto ao vivo.
Grava alertas no assistente_alertas se algum gatilho disparar.
"""
from servicos.agendador import rotina_gatilhos_carteira

rotina_gatilhos_carteira()