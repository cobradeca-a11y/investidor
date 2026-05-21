"""
api/assistente.py

Endpoints do assistente financeiro de uso diario.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response

from acesso.rate_limit import dependencia_rate_limit
from acesso.seguranca import verificar_api_key, resposta_erro_segura
from servicos import assistente_financeiro
from sistema import observabilidade

router = APIRouter(
    prefix="/api/assistente",
    tags=["assistente"],
    dependencies=[Depends(verificar_api_key), Depends(dependencia_rate_limit("sensivel"))],
)


@router.get("/fundos/{ticker}")
def detalhe_fundo(ticker: str) -> dict[str, Any]:
    try:
        return assistente_financeiro.detalhe_fundo(ticker)
    except Exception as erro:
        observabilidade.registrar_erro("api.assistente.detalhe_fundo", erro, ticker=ticker)
        return resposta_erro_segura("Falha controlada ao consultar detalhe do fundo.", ticker=ticker)


@router.get("/fundos/{ticker}/evolucao")
def evolucao_fundo(ticker: str) -> dict[str, Any]:
    try:
        return assistente_financeiro.evolucao_fundo(ticker)
    except Exception as erro:
        observabilidade.registrar_erro("api.assistente.evolucao_fundo", erro, ticker=ticker)
        return resposta_erro_segura("Falha controlada ao consultar evolucao do fundo.", ticker=ticker)


@router.get("/alertas")
def alertas(tickers: str | None = None) -> dict[str, Any]:
    try:
        lista = [t.strip() for t in tickers.split(",")] if tickers else None
        return assistente_financeiro.gerar_alertas(lista)
    except Exception as erro:
        observabilidade.registrar_erro("api.assistente.alertas", erro)
        return resposta_erro_segura("Falha controlada ao gerar alertas.", alertas=[])


@router.get("/alertas/novos")
def alertas_novos(desde_id: int = 0, limite: int = 20) -> dict[str, Any]:
    try:
        return assistente_financeiro.listar_alertas_novos(desde_id=desde_id, limite=limite)
    except Exception as erro:
        observabilidade.registrar_erro("api.assistente.alertas_novos", erro)
        return resposta_erro_segura("Falha controlada ao consultar alertas novos.", alertas=[])


@router.get("/rebalanceamento")
def rebalanceamento() -> dict[str, Any]:
    try:
        return assistente_financeiro.rebalanceamento()
    except Exception as erro:
        observabilidade.registrar_erro("api.assistente.rebalanceamento", erro)
        return resposta_erro_segura("Falha controlada ao gerar rebalanceamento.", sugestoes=[])


@router.get("/fundos/{ticker}/exportar", response_model=None)
def exportar_fundo(ticker: str, formato: str = "txt") -> dict[str, Any] | Response:
    try:
        exportacao = assistente_financeiro.relatorio_offline(ticker, formato=formato)
        if formato.lower() in {"txt", "md", "markdown", "pdf"}:
            nome = f"fiia_{exportacao['ticker']}.{exportacao['formato']}"
            return Response(
                content=exportacao["conteudo"],
                media_type=exportacao["content_type"],
                headers={"Content-Disposition": f"attachment; filename={nome}"},
            )
        return exportacao
    except Exception as erro:
        observabilidade.registrar_erro("api.assistente.exportar_fundo", erro, ticker=ticker)
        return resposta_erro_segura("Falha controlada ao exportar relatorio do fundo.", ticker=ticker)
