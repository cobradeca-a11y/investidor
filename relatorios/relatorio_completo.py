"""
relatorios/relatorio_completo.py

Compatibilidade dos endpoints existentes de relatórios com a camada auditável.

Regras:
- não aciona scraping;
- não chama motor decisório;
- não altera decisão;
- usa decisões persistidas, carteira local e auditoria existente.
"""
from __future__ import annotations

from typing import Any

from relatorios.relatorios_auditaveis import (
    NAO_DISPONIVEL,
    gerar_relatorio_auditavel_completo,
    gerar_markdown_relatorio_auditavel,
)


def _normalizar_ticker(ticker: str) -> str:
    return str(ticker or "").upper().replace(".SA", "").strip()


def gerar_relatorio_completo(tickers: list[str] | None = None) -> dict[str, Any]:
    """Gera relatório completo auditável, sem scraping e sem motor."""
    relatorio = gerar_relatorio_auditavel_completo(limite=500, incluir_replay=False)
    filtro = {_normalizar_ticker(t) for t in (tickers or []) if _normalizar_ticker(t)}
    decisoes = relatorio.get("decisoes", {}).get("decisoes", [])
    if filtro:
        decisoes = [item for item in decisoes if _normalizar_ticker(item.get("ticker")) in filtro]
    relatorio["status"] = "ok"
    relatorio["analise_individual"] = decisoes
    relatorio["ranking"] = [
        {
            "posicao": idx + 1,
            "ticker": item.get("ticker", NAO_DISPONIVEL),
            "decisao": item.get("decisao", NAO_DISPONIVEL),
            "score_final": item.get("score_final", NAO_DISPONIVEL),
            "contexto_versao": item.get("contexto_versao", NAO_DISPONIVEL),
            "versao_motor": item.get("versao_motor", NAO_DISPONIVEL),
            "payload_hash": item.get("payload_hash", NAO_DISPONIVEL),
            "hash_valido": item.get("hash_valido", NAO_DISPONIVEL),
        }
        for idx, item in enumerate(decisoes)
    ]
    relatorio["resumo_executivo"] = {
        "ativos_analisados": len(decisoes),
        "quantidade_decisoes": relatorio.get("decisoes", {}).get("resumo", {}).get("quantidade_decisoes", 0),
        "quantidade_bloqueios": relatorio.get("decisoes", {}).get("resumo", {}).get("quantidade_bloqueios", 0),
        "quantidade_posicoes_carteira": relatorio.get("carteira", {}).get("resumo", {}).get("quantidade_posicoes", 0),
        "sem_scraping": True,
        "executou_motor": False,
        "alterou_decisao": False,
    }
    relatorio["riscos_e_alertas"] = [
        f"{item.get('ticker', NAO_DISPONIVEL)}: hash inválido ou não disponível."
        for item in decisoes
        if item.get("hash_valido") is not True
    ]
    relatorio["tickers_filtrados"] = sorted(filtro)
    relatorio["proximos_passos"] = [
        "Validar CI e testes locais antes de usar o relatório operacionalmente.",
        "Conferir decisões com hash inválido ou não disponível.",
        "Executar replay explícito quando necessário para auditoria aprofundada.",
    ]
    return relatorio


def gerar_markdown_relatorio(relatorio: dict[str, Any]) -> str:
    """Exporta relatório em Markdown."""
    return gerar_markdown_relatorio_auditavel(relatorio)


def gerar_analise_individual(ticker: str) -> dict[str, Any]:
    """Retorna análise auditável individual por ticker a partir de decisões persistidas."""
    ticker_norm = _normalizar_ticker(ticker)
    relatorio = gerar_relatorio_completo([ticker_norm])
    itens = relatorio.get("analise_individual", [])
    if itens:
        item = dict(itens[0])
        item.setdefault("sem_scraping", True)
        item.setdefault("executou_motor", False)
        item.setdefault("alterou_decisao", False)
        return item
    return {
        "ticker": ticker_norm or NAO_DISPONIVEL,
        "status": NAO_DISPONIVEL,
        "decisao": NAO_DISPONIVEL,
        "motivo": NAO_DISPONIVEL,
        "contexto_versao": NAO_DISPONIVEL,
        "versao_motor": NAO_DISPONIVEL,
        "payload_hash": NAO_DISPONIVEL,
        "sem_scraping": True,
        "executou_motor": False,
        "alterou_decisao": False,
    }


def comparar_ativos(tickers: list[str] | None = None) -> list[dict[str, Any]]:
    """Compara ativos por dados auditáveis já persistidos."""
    return gerar_relatorio_completo(tickers or []).get("analise_individual", [])
