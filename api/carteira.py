"""
api/carteira.py

API operacional da carteira do FIIA.

Objetivo:
- expor posições;
- registrar compras e vendas;
- consultar resumo da carteira;
- avaliar política de alocação por ticker/veredito;
- conectar a carteira real à camada de decisão.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from carteira import repositorio_carteira
from carteira.politica_carteira import avaliar_alocacao_sugerida
from decisao.decisao_com_confianca import decidir
from sistema import observabilidade

router = APIRouter(prefix="/api/carteira", tags=["carteira"])


class OperacaoCarteira(BaseModel):
    ticker: str
    quantidade: float = Field(gt=0)
    preco: float = Field(gt=0)
    custos: float = 0.0
    data_operacao: str | None = None
    segmento: str | None = None
    origem: str = "MANUAL"
    observacao: str | None = None


class PoliticaRequest(BaseModel):
    ticker: str
    percentual_atual_ativo: float = 0.0
    percentual_atual_segmento: float = 0.0
    caixa_disponivel_pct: float = 1.0
    segmento: str | None = None


@router.get("/resumo")
def resumo() -> dict[str, Any]:
    try:
        return {"status": "ok", "carteira": repositorio_carteira.resumo_carteira()}
    except Exception as erro:
        observabilidade.registrar_erro("api.carteira.resumo", erro)
        return {"status": "erro", "mensagem": str(erro)}


@router.get("/posicoes")
def posicoes() -> dict[str, Any]:
    try:
        itens = repositorio_carteira.listar_posicoes()
        return {"status": "ok", "quantidade": len(itens), "posicoes": itens}
    except Exception as erro:
        observabilidade.registrar_erro("api.carteira.posicoes", erro)
        return {"status": "erro", "mensagem": str(erro), "posicoes": []}


@router.get("/posicoes/{ticker}")
def posicao(ticker: str) -> dict[str, Any]:
    try:
        item = repositorio_carteira.obter_posicao(ticker)
        return {"status": "ok", "ticker": ticker.upper().replace(".SA", ""), "posicao": item}
    except Exception as erro:
        observabilidade.registrar_erro("api.carteira.posicao", erro, ticker=ticker)
        return {"status": "erro", "ticker": ticker, "mensagem": str(erro)}


@router.post("/compra")
def registrar_compra(payload: OperacaoCarteira) -> dict[str, Any]:
    try:
        resultado = repositorio_carteira.registrar_compra(
            payload.ticker,
            payload.quantidade,
            payload.preco,
            custos=payload.custos,
            data_operacao=payload.data_operacao,
            segmento=payload.segmento,
            origem=payload.origem,
            observacao=payload.observacao,
        )
        return {"status": "ok", "posicao": resultado}
    except Exception as erro:
        observabilidade.registrar_erro("api.carteira.compra", erro, ticker=payload.ticker)
        return {"status": "erro", "mensagem": str(erro)}


@router.post("/venda")
def registrar_venda(payload: OperacaoCarteira) -> dict[str, Any]:
    try:
        resultado = repositorio_carteira.registrar_venda(
            payload.ticker,
            payload.quantidade,
            payload.preco,
            custos=payload.custos,
            data_operacao=payload.data_operacao,
            origem=payload.origem,
            observacao=payload.observacao,
        )
        return {"status": "ok", "posicao": resultado}
    except Exception as erro:
        observabilidade.registrar_erro("api.carteira.venda", erro, ticker=payload.ticker)
        return {"status": "erro", "mensagem": str(erro)}


@router.post("/politica")
def politica(payload: PoliticaRequest) -> dict[str, Any]:
    """Calcula ação de carteira para um ticker usando decisão atual do motor."""
    ticker = payload.ticker.upper().replace(".SA", "")
    try:
        veredito = decidir(ticker)
        gate55 = veredito.get("gate55_confianca_dados", {}) or {}
        resultado = avaliar_alocacao_sugerida(
            ticker=ticker,
            decisao=veredito.get("decisao", "MONITORAR"),
            risco=veredito.get("risco"),
            confianca=veredito.get("confianca"),
            segmento=payload.segmento or veredito.get("segmento"),
            fonte_patrimonial=veredito.get("fonte_patrimonial"),
            gate55_status=gate55.get("status"),
            percentual_atual_ativo=payload.percentual_atual_ativo,
            percentual_atual_segmento=payload.percentual_atual_segmento,
            caixa_disponivel_pct=payload.caixa_disponivel_pct,
        )
        return {"status": "ok", "ticker": ticker, "veredito": veredito, "politica": resultado.to_dict()}
    except Exception as erro:
        observabilidade.registrar_erro("api.carteira.politica", erro, ticker=ticker)
        return {"status": "erro", "ticker": ticker, "mensagem": str(erro)}
