"""
educacao/explicador.py
Transforma scores e decisões técnicas em linguagem simples.
O objetivo é ensinar enquanto informa — sem jargão, sem suposição de conhecimento prévio.
"""
from typing import Optional


def explicar_status(
    status: str,
    ticker: str,
    score_qualidade: Optional[float],
    dy_recorrente_pct: Optional[float],
    preco_atual: Optional[float],
    preco_ideal: Optional[float],
    premio_cdi: Optional[float],
    cdi_atual: Optional[float],
    travas: list[dict],
    alertas: list[str],
) -> str:
    """
    Gera explicação em linguagem simples da decisão do sistema.
    """
    linhas = []
    sep = "─" * 50

    linhas.append(sep)
    linhas.append(f"  ENTENDA A DECISÃO — {ticker}")
    linhas.append(sep)
    linhas.append(f"\n  STATUS: {status}\n")

    # Explicação do status
    explicacoes_status = {
        "ENTRADA_SEGURA": (
            "O sistema identificou que esse ativo tem qualidade adequada, "
            "preço dentro da faixa segura e renda que compensa o risco."
        ),
        "ENTRADA_PARCIAL": (
            "O ativo é bom, mas há alguma incerteza — preço no limite ou "
            "cenário neutro. Uma posição menor é mais prudente agora."
        ),
        "AGUARDAR_PRECO": (
            "O ativo é bom, mas o preço atual está acima do considerado seguro. "
            "Comprar agora seria pagar caro pelo risco."
        ),
        "MONITORAR": (
            "Ativo interessante, mas dados insuficientes ou alguma trava ativa. "
            "Acompanhe sem comprar até a situação se resolver."
        ),
        "MANTER": (
            "Você já tem esse ativo e a tese continua válida. "
            "Não há motivo para vender, mas também não é hora de reforçar."
        ),
        "REDUZIR": (
            "O ativo ficou caro demais, concentrado ou o risco aumentou. "
            "Considere vender parte da posição."
        ),
        "VENDER": (
            "A tese original não se sustenta mais. O motivo pelo qual você "
            "comprou esse ativo mudou. Saída técnica recomendada."
        ),
        "EVITAR": (
            "Ativo com qualidade insuficiente ou risco não compensado pelo retorno."
        ),
        "REVISAO_HUMANA": (
            "Há informações conflitantes ou um evento recente grave que o sistema "
            "não consegue avaliar sozinho. Leia o relatório gerencial antes de decidir."
        ),
    }

    linhas.append("  POR QUÊ ESSE STATUS?")
    linhas.append(f"  → {explicacoes_status.get(status, 'Status não reconhecido.')}")

    # Qualidade
    if score_qualidade is not None:
        nivel = (
            "muito bom" if score_qualidade >= 75 else
            "bom"       if score_qualidade >= 60 else
            "médio"     if score_qualidade >= 45 else
            "fraco"
        )
        linhas.append(f"\n  QUALIDADE DO ATIVO: {score_qualidade:.0f}/100 ({nivel})")

    # Renda recorrente
    if dy_recorrente_pct is not None:
        linhas.append(f"\n  RENDA RECORRENTE ANUAL: {dy_recorrente_pct:.2f}%")
        if cdi_atual:
            linhas.append(f"  CDI ATUAL:              {cdi_atual:.2f}%")
        if premio_cdi is not None:
            sinal = "+" if premio_cdi >= 0 else ""
            linhas.append(f"  PRÊMIO SOBRE CDI:       {sinal}{premio_cdi:.2f} pontos percentuais")
            linhas.append("")
            if premio_cdi >= 0:
                linhas.append(
                    f"  → Esse FII paga {sinal}{premio_cdi:.2f}pp a mais que a renda fixa (CDI), "
                    "compensando o risco adicional."
                )
            else:
                linhas.append(
                    f"  → A renda fixa está pagando {abs(premio_cdi):.2f}pp a MAIS que esse FII, "
                    "com menos risco. O FII precisa estar mais barato."
                )

    # Preço
    if preco_atual and preco_ideal:
        linhas.append(f"\n  PREÇO ATUAL:  R$ {preco_atual:.2f}")
        linhas.append(f"  PREÇO IDEAL:  R$ {preco_ideal:.2f}")
        if preco_atual > preco_ideal:
            diferenca = ((preco_atual / preco_ideal) - 1) * 100
            linhas.append(
                f"\n  → O preço atual está {diferenca:.1f}% acima do ideal. "
                "Comprar agora reduz sua margem de segurança."
            )
        else:
            desconto = ((preco_ideal / preco_atual) - 1) * 100
            linhas.append(
                f"\n  → O preço atual oferece {desconto:.1f}% de desconto sobre o preço ideal. "
                "Boa margem de segurança."
            )

    # Travas
    if travas:
        linhas.append(f"\n  {'TRAVAS ATIVAS':}")
        for t in travas:
            linhas.append(f"  ⚠ {t['nome']}")
            linhas.append(f"    {t['motivo']}")

    # Alertas
    if alertas:
        linhas.append("\n  ALERTAS")
        for a in alertas:
            linhas.append(f"  ! {a}")

    # Glossário contextual
    termos_usados = []
    if dy_recorrente_pct is not None:
        termos_usados.append(("Renda recorrente", "Dividendo que o fundo paga de forma estável todo mês, excluindo valores extraordinários."))
    if premio_cdi is not None:
        termos_usados.append(("Prêmio de risco", "Quanto o FII paga a mais que a renda fixa segura (CDI), compensando o risco maior."))
    if preco_ideal is not None:
        termos_usados.append(("Margem de segurança", "Desconto entre o preço atual e o preço máximo considerado seguro para entrar no ativo."))

    if termos_usados:
        linhas.append("\n  TERMOS USADOS NESSA ANÁLISE")
        for termo, definicao in termos_usados:
            linhas.append(f"  → {termo}: {definicao}")

    linhas.append(sep)
    return "\n".join(linhas)
