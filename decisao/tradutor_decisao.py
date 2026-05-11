"""
decisao/tradutor_decisao.py
Transforma o veredito do motor_decisao em linguagem simples e direta.
Sem jargão, sem economês — só o que o usuário precisa saber para agir.
"""

_EMOJI_DECISAO = {
    "COMPRAR":         "🟢",
    "COMPRAR_PARCIAL": "🟡",
    "AGUARDAR":        "🔵",
    "MANTER":          "⚪",
    "MONITORAR":       "🟠",
    "EVITAR":          "🔴",
}

_LABEL_DECISAO = {
    "COMPRAR":         "COMPRAR",
    "COMPRAR_PARCIAL": "COMPRAR PARCIALMENTE",
    "AGUARDAR":        "AGUARDAR",
    "MANTER":          "MANTER",
    "MONITORAR":       "MONITORAR",
    "EVITAR":          "EVITAR",
}

_LABEL_CONFIANCA = {
    "ALTA":  "Alta ✅",
    "MEDIA": "Média ⚠️",
    "BAIXA": "Baixa ❌",
}

_LABEL_TOM = {
    "otimista":       "Otimista 📈",
    "neutro":         "Neutro ➡️",
    "defensivo":      "Defensivo 📉",
    "nao_disponivel": "Não disponível",
}


def _fmt_reais(valor) -> str:
    if valor is None:
        return "Não disponível"
    return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_pct(valor) -> str:
    """Formata valor já em pontos percentuais (ex: 12.5 → '+12.5%')."""
    if valor is None:
        return "Não disponível"
    sinal = "+" if float(valor) > 0 else ""
    return f"{sinal}{float(valor):.1f}%"


def _fmt_pp(valor) -> str:
    """Formata prêmio em pontos percentuais (ex: 0.75 → '+0.75 pp')."""
    if valor is None:
        return "Não disponível"
    sinal = "+" if float(valor) > 0 else ""
    return f"{sinal}{float(valor):.2f} pp"


def formatar_veredito(v: dict) -> str:
    """
    Recebe o dict do motor_decisao.decidir() e retorna
    uma string formatada para exibição no terminal ou PWA.
    """
    decisao = v.get("decisao", "MONITORAR")
    emoji   = _EMOJI_DECISAO.get(decisao, "⚪")
    label   = _LABEL_DECISAO.get(decisao, decisao)
    ticker  = v.get("ticker", "")
    sep     = "─" * 52

    linhas = [
        "",
        sep,
        f"  {emoji}  VEREDITO FIIA — {ticker}",
        sep,
        "",
        f"  📌 Decisão:       {label}",
        f"  🎯 Confiança:     {_LABEL_CONFIANCA.get(v.get('confianca', 'BAIXA'), '?')}",
        f"  📂 Segmento:      {v.get('segmento', 'Não informado')}",
        "",
        "  💰 PREÇOS",
        f"     Atual:         {_fmt_reais(v.get('preco_atual'))}",
        f"     Justo:         {_fmt_reais(v.get('preco_justo'))}",
        f"     Entrada ideal: {_fmt_reais(v.get('preco_entrada'))}",
        f"     Piso (stress): {_fmt_reais(v.get('preco_stress'))}",
        "",
        "  📊 INDICADORES",
        f"     Margem atual:  {_fmt_pct(v.get('margem'))}",
        f"     Margem stress: {_fmt_pct(v.get('margem_stress'))}",
        f"     P/VP:          {v.get('pvp', 'N/A')}",
        f"     DY 12M:        {_fmt_pct(v.get('dy_12m_pct'))}",
        f"     DY Recorrente: {_fmt_pct(v.get('dy_recorrente_pct'))}",
        f"     % Recorrente:  {_fmt_pct(v.get('pct_recorrente'))}",
        f"     Prêmio CDI:    {_fmt_pp(v.get('premio_cdi'))}",
        f"     Vacância:      {v.get('vacancia', 'N/A')}%",
        "",
        "  🧠 INTELIGÊNCIA IA",
        f"     Score IA:      {v.get('score_ia', '?')}/10  ({v.get('ia_status', 'INDISPONIVEL')})",
        f"     Tom do gestor: {_LABEL_TOM.get(v.get('tom_gestor', 'nao_disponivel'), 'N/A')}",
    ]

    # Riscos da IA
    riscos_ia = v.get("riscos_ia", [])
    if riscos_ia:
        linhas.append("")
        linhas.append("  ⚠️  RISCOS IDENTIFICADOS PELA IA")
        for r in riscos_ia[:3]:
            linhas.append(f"     • {r}")

    # Travas ativas
    alertas = v.get("alertas", [])
    if alertas:
        linhas.append("")
        linhas.append("  🚫 TRAVAS ATIVAS")
        for a in alertas[:3]:
            linhas.append(f"     • {a}")

    # Motivo da decisão
    linhas += [
        "",
        "  📝 MOTIVO",
        f"     {v.get('motivo', '')}",
    ]

    # Ajuste da IA
    if v.get("ajuste_ia"):
        linhas += [
            "",
            "  🔄 AJUSTE DA IA",
            f"     {v['ajuste_ia']}",
        ]

    # Quando revisar
    linhas += [
        "",
        "  🗓️  PRÓXIMA REVISÃO",
        f"     {v.get('revisao', '')}",
        "",
        "  📡 DADOS",
        f"     Confiabilidade: {v.get('confiabilidade', 0)}%  |  "
        f"Histórico: {v.get('meses_historico', 0)} meses  |  "
        f"Modelo: v{v.get('versao_modelo', '?')}",
        f"     Analisado em:   {v.get('data_analise', '')}",
        "",
        sep,
    ]

    return "\n".join(linhas)


def formatar_card_resumido(v: dict) -> str:
    """
    Versão compacta para listagem no radar (uma linha por FII).
    """
    emoji   = _EMOJI_DECISAO.get(v.get("decisao", "MONITORAR"), "⚪")
    label   = _LABEL_DECISAO.get(v.get("decisao", "MONITORAR"), "MONITORAR")
    ticker  = v.get("ticker", "")
    margem  = _fmt_pct(v.get("margem"))
    preco   = _fmt_reais(v.get("preco_atual"))
    entrada = _fmt_reais(v.get("preco_entrada"))
    conf    = v.get("confianca", "?")[0]   # A / M / B
    score   = v.get("score_ia")
    score_str = f"IA:{score}/10" if score is not None else f"IA:{v.get('ia_status', '?')}"

    return (
        f"{emoji} {ticker:<8} {label:<22} "
        f"Margem:{margem}  Preço:{preco}  Entrada:{entrada}  "
        f"Conf:{conf}  {score_str}"
    )
