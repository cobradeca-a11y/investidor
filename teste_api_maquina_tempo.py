from __future__ import annotations

from fastapi.testclient import TestClient

import api.maquina_tempo as api_maquina_tempo
import app as app_mod
from config import settings


def _headers():
    return {"x-api-key": settings.FIIA_API_KEY}


def test_maquina_tempo_exige_api_key(monkeypatch):
    monkeypatch.setattr(settings, "FIIA_API_KEY", "teste-maquina-tempo")
    client = TestClient(app_mod.app)

    resp = client.post("/api/maquina-tempo/backtest", json={"ticker": "HGLG11", "data": "2021-05-20"})

    assert resp.status_code == 401


def test_maquina_tempo_status_retorna_snapshot(monkeypatch):
    monkeypatch.setattr(settings, "FIIA_API_KEY", "teste-maquina-tempo")
    monkeypatch.setattr(
        api_maquina_tempo,
        "buscar_snapshot_historico",
        lambda ticker, data, max_defasagem_dias=45: {
            "snapshot_usado": "2021-05-20",
            "hash_snapshot": "abc",
            "defasagem_dias": 0,
            "validade_institucional": True,
            "motivo_validade": "ok",
            "origem_snapshot": "teste",
        },
    )
    client = TestClient(app_mod.app)

    resp = client.get("/api/maquina-tempo/status?ticker=hglg11&data=2021-05-20", headers=_headers())

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ticker"] == "HGLG11"
    assert payload["snapshot"]["validade_institucional"] is True


def test_maquina_tempo_executa_backtest_controlado(monkeypatch):
    monkeypatch.setattr(settings, "FIIA_API_KEY", "teste-maquina-tempo")
    monkeypatch.setattr(
        api_maquina_tempo.maquina_tempo,
        "executar_backtest_data",
        lambda ticker, data, horizonte_dias=365: {
            "ticker": ticker.upper(),
            "data_referencia": data,
            "horizonte_dias": horizonte_dias,
            "validade_institucional": False,
            "look_ahead_bias": "bloqueado",
            "resultado": {"status": "INVALIDO_SEM_SNAPSHOT_INSTITUCIONAL"},
        },
    )
    client = TestClient(app_mod.app)

    resp = client.post(
        "/api/maquina-tempo/backtest",
        json={"ticker": "mxrf11", "data": "2021-05-20", "horizonte": 365},
        headers=_headers(),
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["modo"] == "ticker"
    assert payload["ticker"] == "MXRF11"
    assert payload["resultado"]["status"] == "INVALIDO_SEM_SNAPSHOT_INSTITUCIONAL"


def test_maquina_tempo_executa_radar_temporal(monkeypatch):
    monkeypatch.setattr(settings, "FIIA_API_KEY", "teste-maquina-tempo")
    monkeypatch.setattr(
        api_maquina_tempo.maquina_tempo,
        "executar_backtest_radar",
        lambda data, top=5, horizonte_dias=365: {
            "data_referencia": data,
            "top": top,
            "horizonte_dias": horizonte_dias,
            "ranking": [],
            "avaliacoes": [],
            "taxa_acerto_pct": None,
        },
    )
    client = TestClient(app_mod.app)

    resp = client.post(
        "/api/maquina-tempo/radar",
        json={"data": "2021-05-20", "top": 5, "horizonte": 365},
        headers=_headers(),
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["modo"] == "radar"
    assert payload["top"] == 5


def test_maquina_tempo_gera_snapshots_temporais(monkeypatch):
    monkeypatch.setattr(settings, "FIIA_API_KEY", "teste-maquina-tempo")
    monkeypatch.setattr(
        api_maquina_tempo,
        "criar_snapshots_historicos_ticker",
        lambda ticker, data_inicio, data_fim, passo_dias=30, origem="api_maquina_tempo": {
            "ticker": ticker.upper(),
            "data_inicio": data_inicio,
            "data_fim": data_fim,
            "passo_dias": passo_dias,
            "total": 2,
            "ok": 2,
            "insuficientes": 0,
            "resultados": [],
        },
    )
    client = TestClient(app_mod.app)

    resp = client.post(
        "/api/maquina-tempo/snapshots",
        json={"ticker": "hglg11", "data_inicio": "2021-01-01", "data_fim": "2021-05-20", "passo_dias": 30},
        headers=_headers(),
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "ok"
    assert payload["ticker"] == "HGLG11"
    assert payload["ok"] == 2
