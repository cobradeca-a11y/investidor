"""
teste_backtest_snapshot.py

Valida o backtest institucional com snapshot histórico:
- decisão usa preço do snapshot, não preço atual;
- ausência de snapshot invalida o ponto e não chama motor;
- todo resultado informa data_referencia, snapshot_usado, validade_institucional e motivo_validade.
"""
from __future__ import annotations

from backtest import maquina_tempo
from aprendizado import snapshots


def _snapshot_valido(preco: float = 100.0) -> dict:
    return {
        "ticker": "HGLG11",
        "data_referencia": "2020-01-10",
        "snapshot_usado": "2020-01-10",
        "hash_snapshot": "hash-snapshot",
        "origem_snapshot": "teste",
        "defasagem_dias": 0,
        "validade_institucional": True,
        "motivo_validade": "Snapshot histórico suficiente para a data de referência.",
        "payload": {
            "snapshot_versao": "snapshot-backtest-v1",
            "ticker": "HGLG11",
            "indicadores": {
                "data": "2020-01-10",
                "preco": preco,
                "vpa": 120.0,
                "pvp": 0.83,
                "patrimonio_liquido": 1_000_000_000.0,
                "liquidez_diaria": 2_500_000.0,
                "ultimo_dividendo": 0.7,
                "dy_12m": 0.08,
                "fonte": "SNAPSHOT_TESTE",
            },
            "fii": {"segmento": "LOGISTICA"},
        },
    }


def test_contexto_decisao_de_snapshot_usa_payload_historico():
    contexto = snapshots.contexto_decisao_de_snapshot(_snapshot_valido(preco=101.25))

    assert contexto is not None
    assert contexto["ticker"] == "HGLG11"
    assert contexto["data"] == "2020-01-10"
    assert contexto["data_referencia"] == "2020-01-10"
    assert contexto["snapshot_usado"] == "2020-01-10"
    assert contexto["hash_snapshot"] == "hash-snapshot"
    assert contexto["preco"] == 101.25
    assert contexto["preco_atual"] == 101.25
    assert contexto["patrimonio_fonte"] == "SNAPSHOT_TESTE"


def test_contexto_decisao_de_snapshot_rejeita_campos_minimos_ausentes():
    snap = _snapshot_valido()
    del snap["payload"]["indicadores"]["preco"]

    assert snapshots.contexto_decisao_de_snapshot(snap) is None


def test_backtest_invalida_sem_snapshot_e_nao_chama_motor(monkeypatch):
    chamadas_motor = []

    monkeypatch.setattr(
        maquina_tempo,
        "buscar_snapshot_historico",
        lambda ticker, data_referencia, max_defasagem_dias=45: {
            "ticker": ticker,
            "data_referencia": data_referencia,
            "snapshot_usado": None,
            "validade_institucional": False,
            "motivo_validade": "Sem snapshot histórico em ou antes da data de referência.",
            "payload": None,
        },
    )
    monkeypatch.setattr(maquina_tempo, "decidir", lambda *args, **kwargs: chamadas_motor.append(args) or {})

    resultado = maquina_tempo.executar_backtest(
        "HGLG11",
        ano_inicio=2020,
        ano_fim=2020,
        dia_mes_decisao="01-10",
    )

    assert resultado["validade_institucional"] is False
    assert resultado["resultados"][0]["data_referencia"] == "2020-01-10"
    assert resultado["resultados"][0]["snapshot_usado"] is None
    assert resultado["resultados"][0]["validade_institucional"] is False
    assert "snapshot" in resultado["resultados"][0]["motivo_validade"].lower()
    assert chamadas_motor == []


def test_backtest_usa_preco_do_snapshot_como_entrada(monkeypatch):
    contextos_recebidos = []

    monkeypatch.setattr(
        maquina_tempo,
        "buscar_snapshot_historico",
        lambda ticker, data_referencia, max_defasagem_dias=45: _snapshot_valido(preco=100.0),
    )
    monkeypatch.setattr(
        maquina_tempo,
        "contexto_decisao_de_snapshot",
        snapshots.contexto_decisao_de_snapshot,
    )
    monkeypatch.setattr(
        maquina_tempo,
        "pegar_preco_historico",
        lambda ticker, data: 130.0,
    )
    monkeypatch.setattr(
        maquina_tempo,
        "_somar_dividendos",
        lambda ticker, inicio, fim: 10.0,
    )
    monkeypatch.setattr(
        maquina_tempo,
        "_cdi_periodo",
        lambda inicio, fim: 0.20,
    )

    def fake_decidir(ticker, contexto=None):
        contextos_recebidos.append(contexto)
        return {
            "ticker": ticker,
            "decisao": "COMPRAR",
            "motivo": "Snapshot aprovado.",
            "gate_parada": 7,
            "trilha_gates": ["G0:APROVADO"],
        }

    monkeypatch.setattr(maquina_tempo, "decidir", fake_decidir)

    resultado = maquina_tempo.executar_backtest(
        "HGLG11",
        ano_inicio=2020,
        ano_fim=2020,
        dia_mes_decisao="01-10",
    )

    item = resultado["resultados"][0]
    assert resultado["validade_institucional"] is True
    assert item["data_referencia"] == "2020-01-10"
    assert item["snapshot_usado"] == "2020-01-10"
    assert item["hash_snapshot"] == "hash-snapshot"
    assert item["validade_institucional"] is True
    assert item["motivo_validade"] == "Snapshot histórico suficiente para a data de referência."
    assert item["preco_entrada"] == 100.0
    assert item["preco_saida"] == 130.0
    assert item["rentabilidade_total_pct"] == 40.0
    assert contextos_recebidos[0]["preco"] == 100.0
    assert contextos_recebidos[0]["snapshot_usado"] == "2020-01-10"


def test_backtest_invalida_snapshot_sem_campos_minimos(monkeypatch):
    snap = _snapshot_valido()
    del snap["payload"]["indicadores"]["vpa"]
    chamadas_motor = []

    monkeypatch.setattr(
        maquina_tempo,
        "buscar_snapshot_historico",
        lambda ticker, data_referencia, max_defasagem_dias=45: snap,
    )
    monkeypatch.setattr(maquina_tempo, "decidir", lambda *args, **kwargs: chamadas_motor.append(args) or {})

    resultado = maquina_tempo.executar_backtest(
        "HGLG11",
        ano_inicio=2020,
        ano_fim=2020,
        dia_mes_decisao="01-10",
    )

    item = resultado["resultados"][0]
    assert item["validade_institucional"] is False
    assert item["snapshot_usado"] == "2020-01-10"
    assert "campos mínimos" in item["motivo_validade"]
    assert chamadas_motor == []
