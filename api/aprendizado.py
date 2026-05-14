"""
api/aprendizado.py

API da camada de aprendizado operacional/tentativa e erro do FIIA.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from aprendizado import tentativa_erro
from sistema import observabilidade

router = APIRouter(prefix="/api/aprendizado", tags=["aprendizado"])


class SimulacaoRequest(BaseModel):
    ticker: str
    acao_simulada: str
    decisao_origem: str | None = None
    segmento: str | None = None
    score_final: float | None = None
    confianca: str | None = None
    risco: str | None = None
    fonte_patrimonial: str | None = None
    gate55_status: str | None = None
    peso_versao: str = "base"
    payload_json: str | None = None


class ResultadoRequest(BaseModel):
    simulacao_id: int
    janela_dias: int = Field(gt=0)
    retorno_pct: float | None = None
    superou_benchmark: bool | None = None
    observacao: str | None = None


class AjustePesoRequest(BaseModel):
    regra: str
    peso_anterior: float
    peso_sugerido: float
    motivo: str
    evidencia: str | None = None


@router.post("/simulacoes")
def registrar_simulacao(payload: SimulacaoRequest) -> dict[str, Any]:
    try:
        simulacao = tentativa_erro.registrar_simulacao(**payload.model_dump())
        return {"status": "ok", "simulacao": simulacao}
    except Exception as erro:
        observabilidade.registrar_erro("api.aprendizado.simulacoes", erro, ticker=payload.ticker)
        return {"status": "erro", "mensagem": str(erro)}


@router.post("/resultados")
def registrar_resultado(payload: ResultadoRequest) -> dict[str, Any]:
    try:
        resultado = tentativa_erro.registrar_resultado(**payload.model_dump())
        return {"status": "ok", "resultado": resultado}
    except Exception as erro:
        observabilidade.registrar_erro("api.aprendizado.resultados", erro)
        return {"status": "erro", "mensagem": str(erro)}


@router.get("/resumo")
def resumo(janela_dias: int | None = None) -> dict[str, Any]:
    try:
        return {"status": "ok", "resumo": tentativa_erro.resumo_aprendizado(janela_dias)}
    except Exception as erro:
        observabilidade.registrar_erro("api.aprendizado.resumo", erro)
        return {"status": "erro", "mensagem": str(erro)}


@router.get("/deterioracao")
def deterioracao(min_amostras: int = 10, limite_falso_positivo: float = 0.35) -> dict[str, Any]:
    try:
        alertas = tentativa_erro.detectar_deterioracao_regra(
            min_amostras=min_amostras,
            limite_falso_positivo=limite_falso_positivo,
        )
        return {"status": "ok", "quantidade": len(alertas), "alertas": alertas}
    except Exception as erro:
        observabilidade.registrar_erro("api.aprendizado.deterioracao", erro)
        return {"status": "erro", "mensagem": str(erro), "alertas": []}


@router.post("/ajustes-peso")
def sugerir_ajuste(payload: AjustePesoRequest) -> dict[str, Any]:
    try:
        ajuste = tentativa_erro.sugerir_ajuste_peso(**payload.model_dump())
        return {"status": "ok", "ajuste": ajuste}
    except Exception as erro:
        observabilidade.registrar_erro("api.aprendizado.ajustes_peso", erro)
        return {"status": "erro", "mensagem": str(erro)}
