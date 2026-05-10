"""
processamento/margem_seguranca.py
Calcula o preço justo do ativo baseado na média histórica de P/VP 
e cruza com o preço atual para descobrir a Margem de Segurança real.
"""
from typing import Optional
from banco import db

from coleta import api_bcb
from processamento.dividendo_recorrente import calcular_dy_recorrente

def calcular_margem_seguranca(ticker: str, cenario_stress: bool = False) -> Optional[float]:
    """
    Camada Sênior: O Motor Quantitativo com Macro-Correlação e Stress Test.
    Retorna a margem de segurança (%).
    """
    ind = db.buscar_um(
        "SELECT preco, vpa FROM indicadores WHERE ticker = ? ORDER BY data DESC LIMIT 1",
        (ticker,)
    )
    fii_info = db.buscar_um("SELECT segmento FROM fiis WHERE ticker = ?", (ticker,))
    
    if not ind or not ind["preco"] or not ind["vpa"] or not fii_info:
        return None
        
    preco_atual = ind["preco"]
    vpa = ind["vpa"]
    segmento = fii_info["segmento"].upper()
    
    # [MACRO SÊNIOR] Taxa de Desconto Dinâmica
    # Um analista sênior exige: MAX(IPCA + 8% , Selic + 1%)
    ipca = api_bcb.obter_ipca_atual() or 4.5
    selic = 10.75 # Fallback (deveria vir de uma API, mas usaremos fixo como proxy por enquanto)
    
    taxa_ipca_plus = (ipca / 100.0) + 0.08
    taxa_selic_plus = (selic / 100.0) + 0.01
    
    taxa_desconto_exigida = max(taxa_ipca_plus, taxa_selic_plus)
    
    if "PAPEL" in segmento or "RECEBÍVEIS" in segmento:
        # Fundo de Papel: Valuation por P/VP com ajuste de stress
        premio_vpa = 1.02 if not cenario_stress else 0.95
        preco_justo = vpa * premio_vpa
    else:
        # Fundo de Tijolo: Valuation por Fluxo de Caixa
        dy_anual = calcular_dy_recorrente(ticker, preco_atual)
        if dy_anual is None:
            preco_justo = vpa * (0.90 if not cenario_stress else 0.75)
        else:
            fluxo_anual_estimado = dy_anual * preco_atual 
            
            # [STRESS TEST] Redução de 15% na receita (vacância/inadimplência)
            if cenario_stress:
                fluxo_anual_estimado *= 0.85
                
            preco_justo = fluxo_anual_estimado / taxa_desconto_exigida
            
    margem = (preco_justo / preco_atual) - 1
    return round(margem, 4)

def relatorio_margem(ticker: str) -> dict:
    ind = db.buscar_um(
        "SELECT preco, vpa FROM indicadores WHERE ticker = ? ORDER BY data DESC LIMIT 1",
        (ticker,)
    )
    fii_info = db.buscar_um("SELECT segmento FROM fiis WHERE ticker = ?", (ticker,))
    
    if not ind or not ind["preco"] or not ind["vpa"] or not fii_info:
        return {"calculavel": False}
        
    preco_atual = ind["preco"]
    segmento = fii_info["segmento"].upper()
    margem = calcular_margem_seguranca(ticker)
    margem_stress = calcular_margem_seguranca(ticker, cenario_stress=True)
    
    if margem is None or margem_stress is None:
        return {"calculavel": False}
        
    preco_justo = preco_atual * (1 + margem)
    preco_stress = preco_atual * (1 + margem_stress)
    
    avaliacao = "POSITIVA" if margem > 0 else "NEGATIVA"
    
    ipca = api_bcb.obter_ipca_atual() or 4.5
    taxa_desconto_exigida = max((ipca/100.0)+0.08, (10.75/100.0)+0.01)
    
    dy_anual = calcular_dy_recorrente(ticker, preco_atual) if "PAPEL" not in segmento and "RECEBÍVEIS" not in segmento else None
    
    return {
        "calculavel": True,
        "preco_atual": preco_atual,
        "preco_justo": preco_justo,
        "preco_stress": preco_stress, # Piso de segurança
        "margem_percentual": margem,
        "avaliacao": avaliacao,
        "segmento": segmento,
        "dy_anual": dy_anual,
        "taxa_desconto": taxa_desconto_exigida
    }
