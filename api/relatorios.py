"""
api/relatorios.py

API de relatórios do FIIA.

Objetivo:
- expor relatório completo estruturado;
- expor versão Markdown;
- permitir análise individual por ticker;
- permitir comparação entre ativos.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from relatorios.relatorio_completo import (
    gerar_relatorio_completo,
    gerar_markdown_relatorio,
    gerar_analise_individual,
    comparar_ativos,
)
from sistema import observabilidade

router = APIRouter(prefix="/api/relatorios", tags=["relatorios"])


class RelatorioRequest(BaseModel):
    tickers: list[str] = []


@router.post("/completo")
def relatorio_completo(payload: RelatorioRequest) -> dict[str, Any]:
    try:
        relatorio = gerar_relatorio_completo(payload.tickers)
        return relatorio
    except Exception as erro:
        observabilidade.registrar_erro("api.relatorios.completo", erro)
        return {"status": "erro", "mensagem": str(erro)}


@router.post("/markdown")
def relatorio_markdown(payload: RelatorioRequest) -> dict[str, Any]:
    try:
        relatorio = gerar_relatorio_completo(payload.tickers)
        markdown = gerar_markdown_relatorio(relatorio)
        return {"status": "ok", "markdown": markdown, "relatorio": relatorio}
    except Exception as erro:
        observabilidade.registrar_erro("api.relatorios.markdown", erro)
        return {"status": "erro", "mensagem": str(erro), "markdown": ""}


@router.get("/ativo/{ticker}")
def relatorio_ativo(ticker: str) -> dict[str, Any]:
    ticker_norm = ticker.upper().replace(".SA", "")
    try:
        return {"status": "ok", "ativo": gerar_analise_individual(ticker_norm)}
    except Exception as erro:
        observabilidade.registrar_erro("api.relatorios.ativo", erro, ticker=ticker_norm)
        return {"status": "erro", "ticker": ticker_norm, "mensagem": str(erro)}


@router.post("/comparar")
def comparar(payload: RelatorioRequest) -> dict[str, Any]:
    try:
        comparacao = comparar_ativos(payload.tickers)
        return {"status": "ok", "quantidade": len(comparacao), "comparacao": comparacao}
    except Exception as erro:
        observabilidade.registrar_erro("api.relatorios.comparar", erro)
        return {"status": "erro", "mensagem": str(erro), "comparacao": []}
