from __future__ import annotations

from fastapi.testclient import TestClient

import api.assistente as api_assistente
import app as app_mod
from config import settings


def _headers():
    return {"x-api-key": settings.FIIA_API_KEY}


def test_assistente_exige_api_key(monkeypatch):
    monkeypatch.setattr(settings, "FIIA_API_KEY", "teste-assistente")
    client = TestClient(app_mod.app)

    resp = client.get("/api/assistente/alertas")

    assert resp.status_code == 401


def test_assistente_endpoints_respondem_payloads_controlados(monkeypatch):
    monkeypatch.setattr(settings, "FIIA_API_KEY", "teste-assistente")
    monkeypatch.setattr(
        api_assistente.assistente_financeiro,
        "detalhe_fundo",
        lambda ticker: {"status": "ok", "ticker": ticker.upper(), "sem_scraping": True},
    )
    monkeypatch.setattr(
        api_assistente.assistente_financeiro,
        "evolucao_fundo",
        lambda ticker: {"status": "ok", "ticker": ticker.upper(), "leitura": "ESTAVEL"},
    )
    monkeypatch.setattr(
        api_assistente.assistente_financeiro,
        "gerar_alertas",
        lambda tickers=None: {"status": "ok", "quantidade": len(tickers or []), "alertas": []},
    )
    monkeypatch.setattr(
        api_assistente.assistente_financeiro,
        "rebalanceamento",
        lambda: {"status": "ok", "quantidade": 0, "sugestoes": []},
    )
    client = TestClient(app_mod.app)

    detalhe = client.get("/api/assistente/fundos/hglg11", headers=_headers())
    evolucao = client.get("/api/assistente/fundos/hglg11/evolucao", headers=_headers())
    alertas = client.get("/api/assistente/alertas?tickers=HGLG11,KNRI11", headers=_headers())
    rebalanceamento = client.get("/api/assistente/rebalanceamento", headers=_headers())

    assert detalhe.status_code == 200
    assert detalhe.json()["ticker"] == "HGLG11"
    assert evolucao.status_code == 200
    assert evolucao.json()["leitura"] == "ESTAVEL"
    assert alertas.status_code == 200
    assert alertas.json()["quantidade"] == 2
    assert rebalanceamento.status_code == 200
    assert rebalanceamento.json()["sugestoes"] == []


def test_assistente_exporta_texto(monkeypatch):
    monkeypatch.setattr(settings, "FIIA_API_KEY", "teste-assistente")
    monkeypatch.setattr(
        api_assistente.assistente_financeiro,
        "relatorio_offline",
        lambda ticker, formato="txt": {
            "status": "ok",
            "ticker": ticker.upper(),
            "formato": "txt",
            "conteudo": "relatorio offline",
            "content_type": "text/plain; charset=utf-8",
        },
    )
    client = TestClient(app_mod.app)

    resp = client.get("/api/assistente/fundos/hglg11/exportar?formato=txt", headers=_headers())

    assert resp.status_code == 200
    assert "relatorio offline" in resp.text
    assert "attachment; filename=fiia_HGLG11.txt" in resp.headers["content-disposition"]
