"""
api/aprendizado.py

API da camada de aprendizado operacional/tentativa e erro do FIIA.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from acesso.seguranca import verificar_api_key, resposta_erro_segura
from aprendizado import tentativa_erro
from aprendizado import ajustes_pesos
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


class DecisaoAjusteRequest(BaseModel):
    usuario: str = Field(min_length=1)
    origem: str = Field(default="API", min_length=1)
    justificativa: str = Field(min_length=1)


@router.post("/simulacoes")
def registrar_simulacao(payload: SimulacaoRequest) -> dict[str, Any]:
    try:
        simulacao = tentativa_erro.registrar_simulacao(**payload.model_dump())
        return {"status": "ok", "simulacao": simulacao}
    except Exception as erro:
        observabilidade.registrar_erro("api.aprendizado.simulacoes", erro, ticker=payload.ticker)
        return resposta_erro_segura("Falha controlada ao registrar simulação.")


@router.post("/resultados")
def registrar_resultado(payload: ResultadoRequest) -> dict[str, Any]:
    try:
        resultado = tentativa_erro.registrar_resultado(**payload.model_dump())
        return {"status": "ok", "resultado": resultado}
    except Exception as erro:
        observabilidade.registrar_erro("api.aprendizado.resultados", erro)
        return resposta_erro_segura("Falha controlada ao registrar resultado.")


@router.get("/resumo")
def resumo(janela_dias: int | None = None) -> dict[str, Any]:
    try:
        return {"status": "ok", "resumo": tentativa_erro.resumo_aprendizado(janela_dias)}
    except Exception as erro:
        observabilidade.registrar_erro("api.aprendizado.resumo", erro)
        return resposta_erro_segura("Falha controlada ao consultar resumo.")


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
        return resposta_erro_segura("Falha controlada ao detectar deterioração.", alertas=[])


@router.post("/ajustes-peso")
def sugerir_ajuste(payload: AjustePesoRequest) -> dict[str, Any]:
    try:
        ajuste = tentativa_erro.sugerir_ajuste_peso(**payload.model_dump())
        return {"status": "ok", "ajuste": ajuste}
    except Exception as erro:
        observabilidade.registrar_erro("api.aprendizado.ajustes_peso", erro)
        return resposta_erro_segura("Falha controlada ao sugerir ajuste.")


@router.get("/ajustes", dependencies=[Depends(verificar_api_key)])
def listar_ajustes(estado: str | None = None, limite: int = 100) -> dict[str, Any]:
    """Lista sugestões controladas de ajuste sem aplicar alterações."""
    try:
        sugestoes = ajustes_pesos.listar_sugestoes(estado=estado, limite=limite)
        return {"status": "ok", "quantidade": len(sugestoes), "sugestoes": sugestoes}
    except Exception as erro:
        observabilidade.registrar_erro("api.aprendizado.listar_ajustes", erro)
        return resposta_erro_segura("Falha controlada ao listar sugestões de ajuste.", sugestoes=[])


@router.post("/ajustes/{sugestao_id}/aprovar", dependencies=[Depends(verificar_api_key)])
def aprovar_ajuste(sugestao_id: int, payload: DecisaoAjusteRequest) -> dict[str, Any]:
    """Aprova sugestão como feedback humano; não altera motor automaticamente."""
    try:
        resultado = ajustes_pesos.aprovar_sugestao(
            sugestao_id,
            usuario=payload.usuario,
            origem=payload.origem,
            justificativa=payload.justificativa,
        )
        return resultado
    except Exception as erro:
        observabilidade.registrar_erro("api.aprendizado.aprovar_ajuste", erro, contexto={"sugestao_id": sugestao_id})
        return resposta_erro_segura("Falha controlada ao aprovar sugestão.")


@router.post("/ajustes/{sugestao_id}/rejeitar", dependencies=[Depends(verificar_api_key)])
def rejeitar_ajuste(sugestao_id: int, payload: DecisaoAjusteRequest) -> dict[str, Any]:
    """Rejeita sugestão como feedback humano; não altera motor automaticamente."""
    try:
        resultado = ajustes_pesos.rejeitar_sugestao(
            sugestao_id,
            usuario=payload.usuario,
            origem=payload.origem,
            justificativa=payload.justificativa,
        )
        return resultado
    except Exception as erro:
        observabilidade.registrar_erro("api.aprendizado.rejeitar_ajuste", erro, contexto={"sugestao_id": sugestao_id})
        return resposta_erro_segura("Falha controlada ao rejeitar sugestão.")


@router.post("/ajustes/{sugestao_id}/expirar", dependencies=[Depends(verificar_api_key)])
def expirar_ajuste(sugestao_id: int, payload: DecisaoAjusteRequest) -> dict[str, Any]:
    """Expira sugestão como feedback humano/operacional; não altera motor automaticamente."""
    try:
        resultado = ajustes_pesos.expirar_sugestao(
            sugestao_id,
            usuario=payload.usuario,
            origem=payload.origem,
            justificativa=payload.justificativa,
        )
        return resultado
    except Exception as erro:
        observabilidade.registrar_erro("api.aprendizado.expirar_ajuste", erro, contexto={"sugestao_id": sugestao_id})
        return resposta_erro_segura("Falha controlada ao expirar sugestão.")
