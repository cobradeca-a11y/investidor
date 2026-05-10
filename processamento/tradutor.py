"""
processamento/tradutor.py
Módulo Educacional: Traduz os indicadores e o veredito do sistema 
para uma linguagem humana, amigável e sem 'economês'.
"""
from typing import List

def explicar_sobrevivencia(aprovado: bool, motivos: List[str]) -> str:
    """Explica os Filtros de Sobrevivência (Camada 1)."""
    if aprovado:
        return "✅ [Filtros de Sobrevivência]: O fundo passou nos testes básicos de segurança. Ele tem boa liquidez (fácil de vender se precisar), vacância sob controle e não está concentrado em poucos imóveis."
    
    texto = "❌ [Alerta de Risco]: O sistema bloqueou a compra deste fundo pelos seguintes motivos de segurança básica:\n"
    for m in motivos:
        texto += f"   - {m}\n"
    texto += "\n   (Não importa se o fundo está 'barato'. Comprar ativos com esses problemas é jogar dinheiro na roleta)."
    return texto

def explicar_valuation(segmento: str, preco_atual: float, preco_justo: float, preco_stress: float, avaliacao: str, dy_anual: float, taxa_desconto: float) -> str:
    """Explica o Motor Quantitativo com visão Sênior (Stress e Macro)."""
    
    eh_tijolo = "PAPEL" not in segmento and "RECEBÍVEIS" not in segmento
    margem = (preco_justo / preco_atual) - 1
    
    if avaliacao == "POSITIVA":
        sinal = "desconto"
        porcentagem = f"{margem*100:.1f}%"
    else:
        sinal = "ágio (mais caro que o valor real)"
        porcentagem = f"{abs(margem)*100:.1f}%"
        
    texto = "🧠 **Tradução FIIA (Nível Sênior):**\n"
    
    if eh_tijolo:
        texto += f"O fundo custa R$ {preco_atual:.2f}. "
        if dy_anual is not None:
            texto += f"Ele paga {dy_anual*100:.1f}% a.a. de dividendo.\n"
            texto += f"Exigimos uma taxa de {taxa_desconto*100:.1f}% a.a. (baseada na Selic/Inflação) para valer o risco.\n"
            texto += f"Preço Justo Alvo: R$ {preco_justo:.2f} ({sinal} de {porcentagem}).\n\n"
            
            texto += f"🛡️ **TESTE DE STRESS:** Em um cenário de crise (queda de 15% na renda), o preço justo seria R$ {preco_stress:.2f}.\n"
            if preco_atual < preco_stress:
                texto += "🚀 Oportunidade Rara: O preço atual é tão baixo que você está protegido até em cenários de crise."
            else:
                texto += "⚠️ Atenção: O preço atual está acima do piso de segurança. Fique atento à vacância."
        else:
            texto += "A análise foi feita pelo valor dos ativos (VPA) por falta de histórico de dividendos."
    else:
        texto += f"Fundo de Papel: O Preço Justo é R$ {preco_justo:.2f}. "
        texto += f"Hoje ele está com {sinal} de {porcentagem} frente ao patrimônio."
        
    return texto
