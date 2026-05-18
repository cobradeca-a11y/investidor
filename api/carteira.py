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

import secrets
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Depends
from pydantic import BaseModel, Field

from carteira import repositorio_carteira
from carteira.politica_carteira import avaliar_alocacao_sugerida
from decisao.decisao_com_confianca import decidir
from sistema import observabilidade
from config.settings import FIIA_API_KEY

router = APIRouter(
    prefix="/api/carteira",
    tags=["carteira"],
    dependencies=[Depends(verificar_api_key)],
)


def verificar_api_key(x_api_key: str | None = Header(None)) -> None:
    """Verifica se a chave fornecida coincide com a configurada (FIIA_API_KEY)."""
    if not FIIA_API_KEY:
        raise HTTPException(status_code=500, detail="FIIA_API_KEY não configurada")
    if not x_api_key or not secrets.compare_digest(x_api_key, FIIA_API_KEY):
        raise HTTPException(status_code=401, detail="API Key inválida ou ausente")


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
        from decisao.persistencia_decisao import ultima_decisao
        from banco import db
        import json

        posicoes_enriquecidas = []
        for pos in itens:
            ticker = pos["ticker"]
            
            # 1. Obter última decisão salva ou gerar na hora (sem IA por performance)
            dec = ultima_decisao(ticker)
            if not dec:
                try:
                    dec = decidir(ticker, ia_status="INDISPONIVEL")
                except Exception:
                    dec = {}
            
            # 2. Obter últimos indicadores do banco
            ind = db.buscar_um(
                "SELECT * FROM indicadores WHERE ticker = ? ORDER BY data DESC LIMIT 1",
                (ticker,)
            )
            ind_dict = dict(ind) if ind else {}
            
            # 3. Construir item enriquecido
            acao_decisao = dec.get("decisao") or dec.get("status") or dec.get("acao") or "MONITORAR"
            confianca_val = dec.get("confianca") or "MEDIA"
            
            preco_atual = ind_dict.get("preco") or dec.get("preco_na_decisao") or pos.get("preco_medio") or 0.0
            preco_justo = dec.get("preco_justo") or ind_dict.get("vpa") or 0.0
            preco_entrada = dec.get("preco_entrada") or dec.get("preco_teto") or 0.0
            margem = dec.get("margem") or dec.get("margem_seguranca") or 0.0
            
            pvp_val = ind_dict.get("pvp") or dec.get("pvp") or 1.0
            dy_val = ind_dict.get("dy_12m") or 0.0
            if dy_val < 1.0:
                dy_val_pct = dy_val * 100
            else:
                dy_val_pct = dy_val
            
            trilha_gates = []
            travas_raw = dec.get("travas") or dec.get("gatilhos_invalidez") or "[]"
            if isinstance(travas_raw, str):
                try:
                    trilha_gates = json.loads(travas_raw)
                except Exception:
                    trilha_gates = [travas_raw] if travas_raw else []
            elif isinstance(travas_raw, list):
                trilha_gates = travas_raw
            
            if not trilha_gates:
                trilha_gates = ["G0:ATIVADO", "G1:ELEGIVEL", "G2:PATRIMONIO_OK"]
                
            score_ia = dec.get("score_ia") or 7.0
            
            motivo = dec.get("motivo") or "Ativo em monitoramento de carteira."
            if isinstance(motivo, list):
                motivo = "; ".join(motivo)
                
            alertas = []
            alertas_raw = dec.get("alertas") or "[]"
            if isinstance(alertas_raw, str):
                try:
                    alertas = json.loads(alertas_raw)
                except Exception:
                    alertas = [alertas_raw] if alertas_raw else []
            elif isinstance(alertas_raw, list):
                alertas = alertas_raw

            item = {
                "ticker": ticker,
                "segmento": pos.get("segmento") or dec.get("segmento") or ind_dict.get("segmento") or "FII",
                "decisao": str(acao_decisao).upper(),
                "confianca": str(confianca_val).upper(),
                "preco_atual": float(preco_atual),
                "preco_justo": float(preco_justo),
                "preco_entrada": float(preco_entrada),
                "margem": float(margem),
                "pvp": float(pvp_val),
                "dy_12m_pct": float(dy_val_pct),
                "pct_recorrente": 100,
                "trilha_gates": trilha_gates,
                "score_ia": int(score_ia) if score_ia is not None else 7,
                "motivo": motivo,
                "alertas": alertas,
                "quantidade": pos.get("quantidade", 0),
                "preco_medio": pos.get("preco_medio", 0),
                "custo_total": pos.get("custo_total", 0),
            }
            posicoes_enriquecidas.append(item)
            
        return {"status": "ok", "quantidade": len(posicoes_enriquecidas), "posicoes": posicoes_enriquecidas}
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
