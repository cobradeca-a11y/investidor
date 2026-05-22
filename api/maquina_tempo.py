"""
api/maquina_tempo.py

Endpoints da Maquina do Tempo.

Esta camada nao recalibra parametros automaticamente. Ela expõe o laboratorio
historico para a PWA usando o mesmo motor institucional do CLI, mantendo o
bloqueio anti-look-ahead quando nao houver snapshot valido.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from acesso.rate_limit import dependencia_rate_limit
from acesso.seguranca import resposta_erro_segura, verificar_api_key
from aprendizado.snapshots import buscar_snapshot_historico, criar_snapshots_historicos_ticker
from backtest import maquina_tempo
from sistema import observabilidade


router = APIRouter(
    prefix="/api/maquina-tempo",
    tags=["maquina-tempo"],
    dependencies=[Depends(verificar_api_key), Depends(dependencia_rate_limit("sensivel"))],
)


class BacktestRequest(BaseModel):
    ticker: str = Field(..., min_length=5, max_length=12)
    data: str = Field(..., min_length=10, max_length=10)
    horizonte: int = Field(default=365, ge=30, le=3650)


class RadarTemporalRequest(BaseModel):
    data: str = Field(..., min_length=10, max_length=10)
    top: int = Field(default=5, ge=1, le=30)
    horizonte: int = Field(default=365, ge=30, le=3650)


class SnapshotTemporalRequest(BaseModel):
    ticker: str = Field(..., min_length=5, max_length=12)
    data_inicio: str = Field(..., min_length=10, max_length=10)
    data_fim: str = Field(..., min_length=10, max_length=10)
    passo_dias: int = Field(default=30, ge=1, le=365)


@router.get("/status")
def status_temporal(ticker: str, data: str, max_defasagem_dias: int = 45) -> dict[str, Any]:
    """Mostra se existe snapshot institucional para ticker/data antes de rodar o backtest."""
    try:
        snapshot = buscar_snapshot_historico(ticker, data, max_defasagem_dias=max_defasagem_dias)
        return {
            "status": "ok",
            "ticker": ticker.upper().replace(".SA", "").strip(),
            "data": data,
            "snapshot": {
                "existe": bool(snapshot.get("snapshot_usado")),
                "data_snapshot": snapshot.get("snapshot_usado"),
                "hash_snapshot": snapshot.get("hash_snapshot"),
                "defasagem_dias": snapshot.get("defasagem_dias"),
                "validade_institucional": snapshot.get("validade_institucional"),
                "motivo_validade": snapshot.get("motivo_validade"),
                "origem_snapshot": snapshot.get("origem_snapshot"),
            },
            "look_ahead_bias": "bloqueado se validade_institucional=false",
        }
    except Exception as erro:
        observabilidade.registrar_erro("api.maquina_tempo.status", erro, ticker=ticker)
        return resposta_erro_segura("Falha controlada ao consultar status temporal.", ticker=ticker, data=data)


@router.post("/backtest")
def backtest_ticker(payload: BacktestRequest) -> dict[str, Any]:
    """Executa Maquina do Tempo para um ativo e uma data historica."""
    try:
        resultado = maquina_tempo.executar_backtest_data(
            payload.ticker,
            payload.data,
            horizonte_dias=payload.horizonte,
        )
        return {"status": "ok", "modo": "ticker", **resultado}
    except Exception as erro:
        observabilidade.registrar_erro("api.maquina_tempo.backtest", erro, ticker=payload.ticker)
        return resposta_erro_segura("Falha controlada ao executar Maquina do Tempo.", ticker=payload.ticker)


@router.post("/radar")
def radar_temporal(payload: RadarTemporalRequest) -> dict[str, Any]:
    """Executa ranking temporal top N com snapshots disponiveis em T0."""
    try:
        resultado = maquina_tempo.executar_backtest_radar(
            payload.data,
            top=payload.top,
            horizonte_dias=payload.horizonte,
        )
        return {"status": "ok", "modo": "radar", **resultado}
    except Exception as erro:
        observabilidade.registrar_erro("api.maquina_tempo.radar", erro)
        return resposta_erro_segura("Falha controlada ao executar radar temporal.", data=payload.data)


@router.post("/snapshots")
def gerar_snapshots_temporais(payload: SnapshotTemporalRequest) -> dict[str, Any]:
    """Gera snapshots locais para um ativo sem consultar fontes externas."""
    try:
        resultado = criar_snapshots_historicos_ticker(
            payload.ticker,
            payload.data_inicio,
            payload.data_fim,
            passo_dias=payload.passo_dias,
            origem="api_maquina_tempo",
        )
        return {"status": "ok", **resultado}
    except Exception as erro:
        observabilidade.registrar_erro("api.maquina_tempo.snapshots", erro, ticker=payload.ticker)
        return resposta_erro_segura("Falha controlada ao gerar snapshots temporais.", ticker=payload.ticker)
