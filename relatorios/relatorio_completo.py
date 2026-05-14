"""
relatorios/relatorio_completo.py

Relatórios completos do FIIA com degradação controlada por seção.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from aprendizado.avaliador import taxa_acerto
from aprendizado.tentativa_erro import resumo_aprendizado, detectar_deterioracao_regra
from carteira.repositorio_carteira import resumo_carteira
from decisao.decisao_com_confianca import decidir
from mercado.cenario_macro import obter_cenario_macro
from sistema import observabilidade


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coleta_segura(nome: str, fn: Callable, fallback: Any, *args, **kwargs) -> tuple[Any, dict[str, Any] | None]:
    """Executa uma seção do relatório sem derrubar o relatório inteiro."""
    try:
        return fn(*args, **kwargs), None
    except Exception as erro:
        observabilidade.registrar_erro(
            "relatorios.completo",
            erro,
            contexto={"secao": nome},
        )
        return fallback, {"secao": nome, "erro": str(erro)}


def gerar_analise_individual(ticker: str) -> dict[str, Any]:
    ticker_norm = ticker.upper().replace(".SA", "").strip()
    veredito = decidir(ticker_norm)
    gate55 = veredito.get("gate55_confianca_dados", {}) or {}
    patrimonio = veredito.get("patrimonio_resolvido", {}) or {}

    return {
        "ticker": ticker_norm,
        "decisao": veredito.get("decisao"),
        "decisao_original": veredito.get("decisao_original"),
        "motivo": veredito.get("motivo"),
        "risco": veredito.get("risco"),
        "confianca": veredito.get("confianca"),
        "score_final": veredito.get("score_final"),
        "margem": veredito.get("margem"),
        "fonte_patrimonial": veredito.get("fonte_patrimonial"),
        "usou_cvm_patrimonial": veredito.get("usou_cvm_patrimonial"),
        "fallback_patrimonial_usado": veredito.get("fallback_patrimonial_usado"),
        "gate55_status": gate55.get("status"),
        "gate55_motivo": gate55.get("motivo"),
        "score_confianca_dados": veredito.get("score_confianca_dados_consolidado") or veredito.get("score_confianca_dados"),
        "nivel_uso_dados": veredito.get("nivel_uso_dados_consolidado") or veredito.get("nivel_uso_dados"),
        "patrimonio": {
            "pvp_cvm": veredito.get("pvp_cvm"),
            "valor_patrimonial_cota_cvm": veredito.get("valor_patrimonial_cota_cvm"),
            "patrimonio_liquido_cvm": veredito.get("patrimonio_liquido_cvm"),
            "competencia_cvm": patrimonio.get("competencia_cvm"),
        },
        "trilha_gates": veredito.get("trilha_gates", []),
        "gates_detalhes": veredito.get("gates_detalhes", {}),
    }


def comparar_ativos(tickers: list[str]) -> list[dict[str, Any]]:
    """Compara ativos mantendo registro de erro por ticker quando uma análise falhar."""
    analises: list[dict[str, Any]] = []

    for ticker in tickers:
        try:
            analises.append(gerar_analise_individual(ticker))
        except Exception as erro:
            ticker_norm = ticker.upper().replace(".SA", "").strip()
            observabilidade.registrar_erro(
                "relatorios.comparar_ativos",
                erro,
                ticker=ticker_norm,
            )
            analises.append(
                {
                    "ticker": ticker_norm,
                    "decisao": "ERRO_ANALISE",
                    "erro": str(erro),
                    "margem": None,
                    "score_final": None,
                    "score_confianca_dados": 0,
                }
            )

    return sorted(
        analises,
        key=lambda item: (
            0 if item.get("erro") else 1,
            item.get("margem") if item.get("margem") is not None else -999,
            item.get("score_final") if item.get("score_final") is not None else -999,
        ),
        reverse=True,
    )


def gerar_relatorio_completo(tickers: list[str] | None = None) -> dict[str, Any]:
    tickers = tickers or []
    falhas: list[dict[str, Any]] = []

    analises, falha = _coleta_segura("analise_ativos", comparar_ativos, [], tickers) if tickers else ([], None)
    if falha:
        falhas.append(falha)

    carteira, falha = _coleta_segura("carteira", resumo_carteira, {"quantidade_ativos": 0, "custo_total": 0, "por_segmento": {}, "posicoes": []})
    if falha:
        falhas.append(falha)

    cenario_macro, falha = _coleta_segura(
        "cenario_macro",
        obter_cenario_macro,
        {"regime_juros": "INDISPONIVEL", "regime_inflacao": "INDISPONIVEL", "impacto_fiis": {"alertas": []}},
    )
    if falha:
        falhas.append(falha)

    aprendizado_90, falha = _coleta_segura("taxa_acerto_90d", taxa_acerto, {"janela_dias": 90, "total": 0, "acerto_pct": 0}, 90)
    if falha:
        falhas.append(falha)

    aprendizado_365, falha = _coleta_segura("taxa_acerto_365d", taxa_acerto, {"janela_dias": 365, "total": 0, "acerto_pct": 0}, 365)
    if falha:
        falhas.append(falha)

    tentativa_erro, falha = _coleta_segura("tentativa_erro", resumo_aprendizado, {"total_simulacoes_unicas": 0})
    if falha:
        falhas.append(falha)

    deterioracoes, falha = _coleta_segura("deterioracoes", detectar_deterioracao_regra, [], min_amostras=10)
    if falha:
        falhas.append(falha)

    alertas = []
    for alerta_macro in cenario_macro.get("impacto_fiis", {}).get("alertas", []):
        alertas.append(f"Macro: {alerta_macro}")

    for item in analises:
        if item.get("erro"):
            alertas.append(f"{item['ticker']}: erro na análise individual ({item.get('erro')}).")
        if item.get("fallback_patrimonial_usado"):
            alertas.append(f"{item['ticker']}: fundamento patrimonial em fallback.")
        if item.get("gate55_status") not in {None, "APROVADO_CONFIANCA_DADOS"} and not item.get("erro"):
            alertas.append(f"{item['ticker']}: Gate 5.5 exige atenção ({item.get('gate55_status')}).")

    ranking = [
        {
            "posicao": idx + 1,
            "ticker": item.get("ticker"),
            "decisao": item.get("decisao"),
            "margem": item.get("margem"),
            "score_final": item.get("score_final"),
            "fonte_patrimonial": item.get("fonte_patrimonial"),
            "score_confianca_dados": item.get("score_confianca_dados"),
            "erro": item.get("erro"),
        }
        for idx, item in enumerate(analises)
    ]

    status_relatorio = "parcial" if falhas else "ok"
    relatorio = {
        "status": status_relatorio,
        "gerado_em": _agora_iso(),
        "falhas_parciais": falhas,
        "resumo_executivo": {
            "ativos_analisados": len(analises),
            "ativos_compraveis": sum(1 for a in analises if str(a.get("decisao", "")).startswith("COMPRAR")),
            "ativos_monitorar": sum(1 for a in analises if a.get("decisao") == "MONITORAR"),
            "ativos_com_erro": sum(1 for a in analises if a.get("erro")),
            "alertas": len(alertas),
            "custo_total_carteira": carteira.get("custo_total"),
            "quantidade_ativos_carteira": carteira.get("quantidade_ativos"),
            "regime_juros": cenario_macro.get("regime_juros"),
            "regime_inflacao": cenario_macro.get("regime_inflacao"),
        },
        "ranking": ranking,
        "analise_individual": analises,
        "riscos_e_alertas": alertas,
        "cenario_macro": cenario_macro,
        "carteira": carteira,
        "aprendizado": {
            "taxa_acerto_90d": aprendizado_90,
            "taxa_acerto_365d": aprendizado_365,
            "tentativa_erro": tentativa_erro,
            "deterioracoes": deterioracoes,
        },
        "estrategia_operacional": {
            "regra": "Priorizar ativos com decisão favorável, CVM patrimonial disponível, Gate 5.5 aprovado e margem positiva.",
            "controle": "Aportes devem respeitar política de carteira, caixa mínimo, limite por ativo/segmento e cenário macro.",
        },
        "proximos_passos": [
            "Validar dados oficiais CVM antes de decisão forte.",
            "Registrar simulações para medir falsos positivos e negativos.",
            "Usar cenário macro para ajustar agressividade dos aportes.",
            "Gerar versão exportável em Markdown/PDF futuramente.",
        ],
    }

    observabilidade.registrar_evento(
        "INFO",
        "relatorios.completo",
        "Relatorio completo gerado",
        contexto={"ativos_analisados": len(analises), "alertas": len(alertas), "status": status_relatorio},
    )
    return relatorio


def gerar_markdown_relatorio(relatorio: dict[str, Any]) -> str:
    linhas = []
    linhas.append("# Relatorio FIIA")
    linhas.append("")
    linhas.append(f"Gerado em: {relatorio.get('gerado_em')}")
    linhas.append(f"Status: {relatorio.get('status')}")
    linhas.append("")

    falhas = relatorio.get("falhas_parciais", [])
    if falhas:
        linhas.append("## Falhas parciais")
        for falha in falhas:
            linhas.append(f"- {falha.get('secao')}: {falha.get('erro')}")
        linhas.append("")

    resumo = relatorio.get("resumo_executivo", {})
    macro = relatorio.get("cenario_macro", {})
    linhas.append("## Resumo executivo")
    linhas.append(f"- Ativos analisados: {resumo.get('ativos_analisados')}")
    linhas.append(f"- Ativos compraveis: {resumo.get('ativos_compraveis')}")
    linhas.append(f"- Ativos em monitoramento: {resumo.get('ativos_monitorar')}")
    linhas.append(f"- Ativos com erro: {resumo.get('ativos_com_erro')}")
    linhas.append(f"- Alertas: {resumo.get('alertas')}")
    linhas.append(f"- Custo total da carteira: {resumo.get('custo_total_carteira')}")
    linhas.append(f"- Regime de juros: {macro.get('regime_juros')}")
    linhas.append(f"- Regime de inflação: {macro.get('regime_inflacao')}")
    linhas.append("")

    linhas.append("## Cenário macro")
    linhas.append(f"- SELIC: {macro.get('selic')}")
    linhas.append(f"- CDI: {macro.get('cdi')}")
    linhas.append(f"- IPCA: {macro.get('ipca')}")
    for alerta in macro.get("impacto_fiis", {}).get("alertas", []):
        linhas.append(f"- {alerta}")
    linhas.append("")

    linhas.append("## Ranking")
    for item in relatorio.get("ranking", []):
        erro = f" | erro={item.get('erro')}" if item.get("erro") else ""
        linhas.append(
            f"{item.get('posicao')}. {item.get('ticker')} - {item.get('decisao')} | margem={item.get('margem')} | confianca={item.get('score_confianca_dados')}{erro}"
        )
    linhas.append("")

    linhas.append("## Análise individual")
    analises = relatorio.get("analise_individual", [])
    if analises:
        for item in analises:
            linhas.append(f"### {item.get('ticker')}")
            if item.get("erro"):
                linhas.append(f"- Erro: {item.get('erro')}")
                linhas.append("")
                continue
            linhas.append(f"- Decisão: {item.get('decisao')}")
            linhas.append(f"- Motivo: {item.get('motivo')}")
            linhas.append(f"- Risco: {item.get('risco')}")
            linhas.append(f"- Margem: {item.get('margem')}")
            linhas.append(f"- Fonte patrimonial: {item.get('fonte_patrimonial')}")
            linhas.append(f"- Gate 5.5: {item.get('gate55_status')}")
            linhas.append(f"- Confiança dos dados: {item.get('score_confianca_dados')}")
            linhas.append("")
    else:
        linhas.append("- Nenhuma análise individual registrada.")
        linhas.append("")

    linhas.append("## Alertas")
    alertas = relatorio.get("riscos_e_alertas", [])
    if alertas:
        for alerta in alertas:
            linhas.append(f"- {alerta}")
    else:
        linhas.append("- Nenhum alerta critico registrado.")
    linhas.append("")

    linhas.append("## Proximos passos")
    for passo in relatorio.get("proximos_passos", []):
        linhas.append(f"- {passo}")

    return "\n".join(linhas)
