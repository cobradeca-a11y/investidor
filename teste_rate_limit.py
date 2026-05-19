"""
teste_rate_limit.py

Valida proteção operacional de rate limit sem disparar scraping, coleta ou motor.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from acesso import rate_limit
from api import auditoria as api_auditoria
from api import carteira as api_carteira
from config import settings


class ClienteFake:
    def __init__(self, host: str):
        self.host = host


class RequestFake:
    def __init__(self, host: str = "127.0.0.1"):
        self.client = ClienteFake(host)


def test_rate_limit_desligado_por_padrao_nao_bloqueia(monkeypatch):
    rate_limit.limpar_rate_limit()
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)

    for _ in range(10):
        assert rate_limit.verificar_rate_limit(RequestFake(), escopo="sensivel", limite=1) is None


def test_rate_limit_bloqueia_quando_configurado(monkeypatch):
    rate_limit.limpar_rate_limit()
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_WINDOW_SECONDS", 60)

    assert rate_limit.verificar_rate_limit(RequestFake(), escopo="sensivel", limite=2) is None
    assert rate_limit.verificar_rate_limit(RequestFake(), escopo="sensivel", limite=2) is None

    with pytest.raises(HTTPException) as exc:
        rate_limit.verificar_rate_limit(RequestFake(), escopo="sensivel", limite=2)

    assert exc.value.status_code == 429
    assert "Muitas requisições" in exc.value.detail


def test_rate_limit_separa_escopos(monkeypatch):
    rate_limit.limpar_rate_limit()
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_WINDOW_SECONDS", 60)

    assert rate_limit.verificar_rate_limit(RequestFake(), escopo="sensivel", limite=1) is None
    assert rate_limit.verificar_rate_limit(RequestFake(), escopo="radar", limite=1) is None

    with pytest.raises(HTTPException):
        rate_limit.verificar_rate_limit(RequestFake(), escopo="sensivel", limite=1)
    with pytest.raises(HTTPException):
        rate_limit.verificar_rate_limit(RequestFake(), escopo="radar", limite=1)


def test_rate_limit_usa_hash_sem_expor_api_key(monkeypatch):
    rate_limit.limpar_rate_limit()
    eventos = []
    segredo = "segredo-super-sensivel"

    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_WINDOW_SECONDS", 60)
    monkeypatch.setattr(rate_limit.observabilidade, "registrar_evento", lambda *args, **kwargs: eventos.append({"args": args, "kwargs": kwargs}))

    rate_limit.verificar_rate_limit(RequestFake(), escopo="sensivel", limite=1, x_api_key=segredo)
    with pytest.raises(HTTPException):
        rate_limit.verificar_rate_limit(RequestFake(), escopo="sensivel", limite=1, x_api_key=segredo)

    assert eventos
    texto_evento = str(eventos[0])
    assert segredo not in texto_evento
    assert "cliente_hash" in texto_evento
    assert "limite" in texto_evento


def test_dependencia_rate_limit_noop_sem_config(monkeypatch):
    rate_limit.limpar_rate_limit()
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)

    dependencia = rate_limit.dependencia_rate_limit("sensivel", limite=1)

    for _ in range(5):
        assert dependencia(RequestFake(), x_api_key="qualquer") is None


def test_dependencia_rate_limit_bloqueia_com_config(monkeypatch):
    rate_limit.limpar_rate_limit()
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_WINDOW_SECONDS", 60)

    dependencia = rate_limit.dependencia_rate_limit("sensivel", limite=1)
    assert dependencia(RequestFake(), x_api_key="chave") is None

    with pytest.raises(HTTPException) as exc:
        dependencia(RequestFake(), x_api_key="chave")

    assert exc.value.status_code == 429


def test_api_carteira_tem_rate_limit_no_router():
    dependencias = [dep.dependency for dep in api_carteira.router.dependencies]

    assert api_carteira.verificar_api_key in dependencias
    assert any(getattr(dep, "__name__", "") == "_dependencia" for dep in dependencias)


def test_api_auditoria_auditavel_tem_rate_limit_configurado():
    rotas_auditaveis = [
        rota for rota in api_auditoria.router.routes
        if getattr(rota, "path", "") in {
            "/api/auditoria/decisoes/auditaveis",
            "/api/auditoria/decisoes/{decisao_id}/auditavel",
        }
    ]

    assert len(rotas_auditaveis) == 2
    for rota in rotas_auditaveis:
        dependencias = [dep.dependency for dep in rota.dependencies]
        assert api_auditoria.verificar_api_key in dependencias
        assert any(getattr(dep, "__name__", "") == "_dependencia" for dep in dependencias)
