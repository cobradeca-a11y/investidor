"""
api/fnet.py

API da camada FNET/CVM documental.

Objetivo:
- importar metadados FNET a partir de arquivo local;
- listar documentos por ticker ou CNPJ;
- expor risco documental operacional por ticker;
- permitir uso da camada FNET fora do motor de decisão.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from acesso.autenticacao import verificar_api_key
from pydantic import BaseModel, Field

from coleta import cvm_fnet_documentos
from processamento.eventos_fnet import analisar_eventos_ticker
from sistema import observabilidade

router = APIRouter(prefix="/api/fnet", tags=["fnet"], dependencies=[Depends(verificar_api_key)])


class ImportarFnetRequest(BaseModel):
    caminho_arquivo: str = Field(..., description="Caminho local do arquivo CSV/XLSX/JSON com metadados FNET")


@router.post("/importar")
def importar_documentos(payload: ImportarFnetRequest) -> dict[str, Any]:
    try:
        resultado = cvm_fnet_documentos.importar_arquivo(payload.caminho_arquivo)
        status = "erro" if resultado.get("erro") else "ok"
        return {"status": status, "resultado": resultado}
    except Exception as erro:
        observabilidade.registrar_erro("api.fnet.importar", erro)
        return {"status": "erro", "mensagem": str(erro)}


@router.get("/ticker/{ticker}")
def documentos_por_ticker(ticker: str, limite: int = 50) -> dict[str, Any]:
    ticker_norm = ticker.upper().replace(".SA", "")
    try:
        docs = cvm_fnet_documentos.listar_por_ticker(ticker_norm, limite=limite)
        return {"status": "ok", "ticker": ticker_norm, "quantidade": len(docs), "documentos": docs}
    except Exception as erro:
        observabilidade.registrar_erro("api.fnet.ticker", erro, ticker=ticker_norm)
        return {"status": "erro", "ticker": ticker_norm, "mensagem": str(erro), "documentos": []}


@router.get("/cnpj/{cnpj_fundo}")
def documentos_por_cnpj(cnpj_fundo: str, limite: int = 50) -> dict[str, Any]:
    try:
        docs = cvm_fnet_documentos.listar_por_cnpj(cnpj_fundo, limite=limite)
        return {"status": "ok", "cnpj_fundo": cnpj_fundo, "quantidade": len(docs), "documentos": docs}
    except Exception as erro:
        observabilidade.registrar_erro("api.fnet.cnpj", erro, contexto={"cnpj_fundo": cnpj_fundo})
        return {"status": "erro", "cnpj_fundo": cnpj_fundo, "mensagem": str(erro), "documentos": []}


@router.get("/risco/{ticker}")
def risco_documental(ticker: str, limite: int = 20, dias_recencia: int = 90) -> dict[str, Any]:
    ticker_norm = ticker.upper().replace(".SA", "")
    try:
        risco = analisar_eventos_ticker(ticker_norm, limite=limite, dias_recencia=dias_recencia)
        return {"status": "ok", "ticker": ticker_norm, "risco_documental": risco}
    except Exception as erro:
        observabilidade.registrar_erro("api.fnet.risco", erro, ticker=ticker_norm)
        return {"status": "erro", "ticker": ticker_norm, "mensagem": str(erro)}
