"""
api/relatorios.py

API de relatórios do FIIA.

Objetivo:
- expor relatório completo estruturado;
- expor versão Markdown;
- permitir análise individual por ticker;
- permitir comparação entre ativos;
- exportar CSV/JSON auditável;
- incluir explicação simples para decisões técnicas.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from acesso.seguranca import verificar_api_key, resposta_erro_segura
from educacao.explicador import explicar_status
from relatorios.relatorio_completo import (
    gerar_relatorio_completo,
    gerar_markdown_relatorio,
    gerar_analise_individual,
    comparar_ativos,
)
from relatorios.exportacao_relatorios import gerar_exportacao
from sistema import observabilidade

router = APIRouter(prefix="/api/relatorios", tags=["relatorios"])


class RelatorioRequest(BaseModel):
    tickers: list[str] = []


def _travas_para_explicador(analise: dict[str, Any]) -> list[dict[str, str]]:
    travas: list[dict[str, str]] = []
    for gate, detalhe in (analise.get("gates_detalhes") or {}).items():
        status = str(detalhe.get("status", ""))
        if "BLOQUEADO" in status or "ELIMINADO" in status:
            travas.append({
                "nome": f"Gate {gate}: {status}",
                "motivo": detalhe.get("motivo") or "Trava técnica ativa.",
            })
    return travas


def _adicionar_explicacao_simples(analise: dict[str, Any]) -> dict[str, Any]:
    try:
        analise["explicacao_simples"] = explicar_status(
            status=analise.get("decisao") or analise.get("status") or "INDEFINIDO",
            ticker=analise.get("ticker") or "",
            score_qualidade=analise.get("score_final") or analise.get("score_qualidade"),
            dy_recorrente_pct=analise.get("dy_recorrente_pct"),
            preco_atual=analise.get("preco_atual"),
            preco_ideal=analise.get("preco_justo") or analise.get("preco_entrada"),
            premio_cdi=analise.get("premio_cdi"),
            cdi_atual=analise.get("cdi_atual"),
            travas=_travas_para_explicador(analise),
            alertas=analise.get("alertas") or [],
        )
    except Exception as erro:
        observabilidade.registrar_erro("api.relatorios.explicador", erro, ticker=analise.get("ticker"))
        analise["explicacao_simples"] = "Explicação simples indisponível para esta análise."
    return analise


@router.post("/completo", dependencies=[Depends(verificar_api_key)])
def relatorio_completo(payload: RelatorioRequest) -> dict[str, Any]:
    try:
        relatorio = gerar_relatorio_completo(payload.tickers)
        for item in relatorio.get("analise_individual", []):
            _adicionar_explicacao_simples(item)
        return relatorio
    except Exception as erro:
        observabilidade.registrar_erro("api.relatorios.completo", erro)
        return resposta_erro_segura("Falha controlada ao gerar relatório completo.")


@router.post("/markdown", dependencies=[Depends(verificar_api_key)])
def relatorio_markdown(payload: RelatorioRequest) -> dict[str, Any]:
    try:
        relatorio = gerar_relatorio_completo(payload.tickers)
        for item in relatorio.get("analise_individual", []):
            _adicionar_explicacao_simples(item)
        markdown = gerar_markdown_relatorio(relatorio)
        return {"status": "ok", "markdown": markdown, "relatorio": relatorio}
    except Exception as erro:
        observabilidade.registrar_erro("api.relatorios.markdown", erro)
        return resposta_erro_segura("Falha controlada ao gerar relatório Markdown.", markdown="")


@router.get("/ativo/{ticker}", dependencies=[Depends(verificar_api_key)])
def relatorio_ativo(ticker: str) -> dict[str, Any]:
    ticker_norm = ticker.upper().replace(".SA", "")
    try:
        analise = gerar_analise_individual(ticker_norm)
        return {"status": "ok", "ativo": _adicionar_explicacao_simples(analise)}
    except Exception as erro:
        observabilidade.registrar_erro("api.relatorios.ativo", erro, ticker=ticker_norm)
        return resposta_erro_segura("Falha controlada ao gerar relatório do ativo.", ticker=ticker_norm)


@router.post("/comparar", dependencies=[Depends(verificar_api_key)])
def comparar(payload: RelatorioRequest) -> dict[str, Any]:
    try:
        comparacao = comparar_ativos(payload.tickers)
        for item in comparacao:
            _adicionar_explicacao_simples(item)
        return {"status": "ok", "quantidade": len(comparacao), "comparacao": comparacao}
    except Exception as erro:
        observabilidade.registrar_erro("api.relatorios.comparar", erro)
        return resposta_erro_segura("Falha controlada ao comparar ativos.", comparacao=[])


@router.get("/exportar", dependencies=[Depends(verificar_api_key)], response_model=None)
def exportar_relatorio(
    formato: str = "json",
    secao: str = "decisoes",
    limite: int = 50,
    incluir_replay: bool = False,
) -> dict[str, Any] | Response:
    """Exporta relatórios auditáveis em JSON ou CSV sem alterar dados."""
    try:
        exportacao = gerar_exportacao(
            formato=formato,
            secao=secao,
            limite=limite,
            incluir_replay=incluir_replay,
        )
        if exportacao.get("status") != "ok":
            return exportacao
        if exportacao.get("formato") == "csv":
            nome = f"fiia_{exportacao.get('secao', 'relatorio')}.csv"
            return Response(
                content=exportacao.get("conteudo", ""),
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": f"attachment; filename={nome}"},
            )
        return exportacao
    except Exception as erro:
        observabilidade.registrar_erro("api.relatorios.exportar", erro)
        return resposta_erro_segura("Falha controlada ao exportar relatório.")
