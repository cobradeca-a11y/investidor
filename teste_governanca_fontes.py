"""
teste_governanca_fontes.py

Testa a governança de fontes sem acionar rede, coleta ou motor decisório.
"""
from __future__ import annotations

from datetime import date

from validacao import governanca_fontes as gf


def test_classificar_fonte_ok():
    resultado = gf.classificar_fonte(
        fonte="CVM",
        disponivel=True,
        data_ultima="2026-05-01",
        data_referencia=date(2026, 5, 19),
        max_idade_dias=30,
    )

    assert resultado["fonte"] == "CVM"
    assert resultado["status"] == "OK"
    assert resultado["idade_dias"] == 18
    assert resultado["score_confianca_fonte"] > 0


def test_classificar_fonte_vencida():
    resultado = gf.classificar_fonte(
        fonte="YAHOO",
        disponivel=True,
        data_ultima="2026-05-01",
        data_referencia=date(2026, 5, 19),
        max_idade_dias=3,
    )

    assert resultado["status"] == "VENCIDA"
    assert "vencida" in resultado["motivo"].lower()


def test_classificar_fonte_divergente():
    resultado = gf.classificar_fonte(
        fonte="FUNDAMENTUS",
        disponivel=True,
        data_ultima="2026-05-18",
        valor_principal=105.0,
        valor_referencia=100.0,
        tolerancia_divergencia_pct=0.02,
        data_referencia=date(2026, 5, 19),
        max_idade_dias=7,
    )

    assert resultado["status"] == "DIVERGENTE"
    assert resultado["divergencia_pct"] == 5.0


def test_classificar_fonte_indisponivel():
    resultado = gf.classificar_fonte(fonte="FNET", disponivel=False)

    assert resultado["status"] == "INDISPONIVEL"
    assert resultado["score_confianca_fonte"] == 0.0


def test_classificar_fonte_suspeita_sem_data():
    resultado = gf.classificar_fonte(fonte="BCB", disponivel=True, data_ultima=None)

    assert resultado["status"] == "SUSPEITA"
    assert "data" in resultado["motivo"].lower()


def test_avaliar_fontes_por_payloads_sem_rede(monkeypatch):
    eventos = []
    monkeypatch.setattr(gf.observabilidade, "registrar_evento", lambda *args, **kwargs: eventos.append({"args": args, "kwargs": kwargs}))

    payloads = {
        "CVM": {"disponivel": True, "data_ultima": "2026-05-01", "max_idade_dias": 60},
        "FNET": {"disponivel": False},
        "YAHOO": {"disponivel": True, "data_ultima": "2026-05-18", "max_idade_dias": 3},
        "FUNDAMENTUS": {
            "disponivel": True,
            "data_ultima": "2026-05-18",
            "valor_principal": 110.0,
            "valor_referencia": 100.0,
            "tolerancia_divergencia_pct": 0.02,
        },
        "BCB": {"disponivel": True, "data_ultima": "2026-05-19", "max_idade_dias": 5},
    }

    consolidado = gf.avaliar_fontes_por_payloads(
        payloads,
        ticker="HGLG11",
        data_referencia="2026-05-19",
        persistir=False,
    )

    assert consolidado["status_global"] == "DIVERGENTE"
    assert consolidado["status_por_fonte"]["CVM"] == "OK"
    assert consolidado["status_por_fonte"]["FNET"] == "INDISPONIVEL"
    assert consolidado["status_por_fonte"]["FUNDAMENTUS"] == "DIVERGENTE"
    assert len(consolidado["fontes"]) == 5
    assert eventos


def test_consolidar_status_fontes_vazio():
    consolidado = gf.consolidar_status_fontes([])

    assert consolidado["status_global"] == "INDISPONIVEL"
    assert consolidado["score_confianca_global"] == 0.0


def test_registrar_status_fonte_sem_persistencia(monkeypatch):
    eventos = []
    chamadas_db = []
    monkeypatch.setattr(gf.observabilidade, "registrar_evento", lambda *args, **kwargs: eventos.append({"args": args, "kwargs": kwargs}))
    monkeypatch.setattr(gf.db, "executar", lambda *args, **kwargs: chamadas_db.append(args))

    status = gf.classificar_fonte(
        fonte="CVM",
        disponivel=True,
        data_ultima="2026-05-10",
        data_referencia=date(2026, 5, 19),
        max_idade_dias=30,
    )
    registrado = gf.registrar_status_fonte(status, ticker="hglg11.sa", data_referencia="2026-05-19", persistir=False)

    assert registrado["ticker"] == "HGLG11"
    assert registrado["status"] == "OK"
    assert eventos
    assert chamadas_db == []


def test_garantir_tabela_governanca_fontes_usa_create_aditivo(monkeypatch):
    sqls = []
    monkeypatch.setattr(gf.db, "executar", lambda sql, params=(): sqls.append(sql))

    gf.garantir_tabela_governanca_fontes()

    texto = "\n".join(sqls).upper()
    assert "CREATE TABLE IF NOT EXISTS GOVERNANCA_FONTES" in texto
    assert "CREATE INDEX IF NOT EXISTS" in texto
    assert "DROP" not in texto
