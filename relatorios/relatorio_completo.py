"""
relatorios/relatorio_completo.py

Relatórios completos do FIIA.

Objetivo:
- resumo executivo;
- ranking;
- análise individual;
- justificativas;
- riscos;
- cenário macro;
- comparação entre ativos;
- estratégia operacional;
- alertas;
- próximos passos.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from aprendizado.avaliador import taxa_acerto
from aprendizado.tentativa_erro import resumo_aprendizado, detectar_deterioracao_regra
from carteira.repositorio_carteira import resumo_carteira
from decisao.decisao_com_confianca import decidir
from sistema import observabilidade


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    analises = [gerar_analise_individual(ticker) for ticker in tickers]
    return sorted(
        analises,
        key=lambda item: (
            item.get("margem") if item.get("margem") is not None else -999,
            item.get("score_final") if item.get("score_final") is not None else -999,
        ),
        reverse=True,
    )


def gerar_relatorio_completo(tickers: list[str] | None = None) -> dict[str, Any]:
    tickers = tickers or []
    analises = comparar_ativos(tickers) if tickers else []
    carteira = resumo_carteira()
    aprendizado_90 = taxa_acerto(90)
    aprendizado_365 = taxa_acerto(365)
    tentativa_erro = resumo_aprendizado()
    deterioracoes = detectar_deterioracao_regra(min_amostras=10)

    alertas = []
    for item in analises:
        if item.get("fallback_patrimonial_usado"):
            alertas.append(f"{item['ticker']}: fundamento patrimonial em fallback.")
        if item.get("gate55_status") not in {None, "APROVADO_CONFIANCA_DADOS"}:
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
        }
        for idx, item in enumerate(analises)
    ]

    relatorio = {
        "status": "ok",
        "gerado_em": _agora_iso(),
        "resumo_executivo": {
            "ativos_analisados": len(analises),
            "ativos_compraveis": sum(1 for a in analises if str(a.get("decisao", "")).startswith("COMPRAR")),
            "ativos_monitorar": sum(1 for a in analises if a.get("decisao") == "MONITORAR"),
            "alertas": len(alertas),
            "custo_total_carteira": carteira.get("custo_total"),
            "quantidade_ativos_carteira": carteira.get("quantidade_ativos"),
        },
        "ranking": ranking,
        "analise_individual": analises,
        "riscos_e_alertas": alertas,
        "cenario_macro": {
            "observacao": "Cenario macro deve ser enriquecido pelo modulo Banco Central/mercado.",
        },
        "carteira": carteira,
        "aprendizado": {
            "taxa_acerto_90d": aprendizado_90,
            "taxa_acerto_365d": aprendizado_365,
            "tentativa_erro": tentativa_erro,
            "deterioracoes": deterioracoes,
        },
        "estrategia_operacional": {
            "regra": "Priorizar ativos com decisao favoravel, CVM patrimonial disponivel, Gate 5.5 aprovado e margem positiva.",
            "controle": "Aportes devem respeitar politica de carteira, caixa minimo e limite por ativo/segmento.",
        },
        "proximos_passos": [
            "Validar dados oficiais CVM antes de decisao forte.",
            "Registrar simulacoes para medir falsos positivos e negativos.",
            "Conectar cenario macro detalhado ao relatorio.",
            "Gerar versao exportavel em Markdown/PDF futuramente.",
        ],
    }

    observabilidade.registrar_evento(
        "INFO",
        "relatorios.completo",
        "Relatorio completo gerado",
        contexto={"ativos_analisados": len(analises), "alertas": len(alertas)},
    )
    return relatorio


def gerar_markdown_relatorio(relatorio: dict[str, Any]) -> str:
    linhas = []
    linhas.append("# Relatorio FIIA")
    linhas.append("")
    linhas.append(f"Gerado em: {relatorio.get('gerado_em')}")
    linhas.append("")
    resumo = relatorio.get("resumo_executivo", {})
    linhas.append("## Resumo executivo")
    linhas.append(f"- Ativos analisados: {resumo.get('ativos_analisados')}")
    linhas.append(f"- Ativos compraveis: {resumo.get('ativos_compraveis')}")
    linhas.append(f"- Ativos em monitoramento: {resumo.get('ativos_monitorar')}")
    linhas.append(f"- Alertas: {resumo.get('alertas')}")
    linhas.append(f"- Custo total da carteira: {resumo.get('custo_total_carteira')}")
    linhas.append("")

    linhas.append("## Ranking")
    for item in relatorio.get("ranking", []):
        linhas.append(
            f"{item.get('posicao')}. {item.get('ticker')} - {item.get('decisao')} | margem={item.get('margem')} | confianca={item.get('score_confianca_dados')}"
        )
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
