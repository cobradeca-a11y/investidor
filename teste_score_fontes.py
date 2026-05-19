"""
teste_score_fontes.py

Valida score histórico de fontes sem rede e sem acoplamento com decisão.
"""
from __future__ import annotations

from datetime import date

from validacao import score_fontes


def test_registrar_score_fonte_sem_persistencia(monkeypatch):
    eventos = []
    chamadas_db = []
    monkeypatch.setattr(score_fontes.observabilidade, "registrar_evento", lambda *args, **kwargs: eventos.append({"args": args, "kwargs": kwargs}))
    monkeypatch.setattr(score_fontes.db, "executar", lambda *args, **kwargs: chamadas_db.append(args))

    registro = score_fontes.registrar_score_fonte(
        fonte="cvm",
        ticker="hglg11.sa",
        data_referencia=date(2026, 5, 19),
        status="OK",
        score=98.456,
        motivo="Fonte dentro do frescor esperado.",
        payload={"origem": "teste"},
        persistir=False,
    )

    assert registro["fonte"] == "CVM"
    assert registro["ticker"] == "HGLG11"
    assert registro["data_referencia"] == "2026-05-19"
    assert registro["status"] == "OK"
    assert registro["score_confianca_fonte"] == 98.46
    assert registro["motivo"] == "Fonte dentro do frescor esperado."
    assert eventos
    assert chamadas_db == []


def test_registrar_score_fonte_normaliza_status_invalido(monkeypatch):
    monkeypatch.setattr(score_fontes.observabilidade, "registrar_evento", lambda *args, **kwargs: None)

    registro = score_fontes.registrar_score_fonte(
        fonte="Yahoo",
        status="QUEBRADO",
        score=120,
        motivo="Status externo desconhecido.",
        persistir=False,
    )

    assert registro["status"] == "SUSPEITA"
    assert registro["score_confianca_fonte"] == 100.0


def test_registrar_score_a_partir_status(monkeypatch):
    monkeypatch.setattr(score_fontes.observabilidade, "registrar_evento", lambda *args, **kwargs: None)

    status_fonte = {
        "fonte": "FNET",
        "status": "INDISPONIVEL",
        "score_confianca_fonte": 0,
        "motivo": "Sem payload.",
        "ticker": "XPTO11",
        "data_referencia": "2026-05-19",
    }
    registro = score_fontes.registrar_score_a_partir_status(status_fonte, persistir=False)

    assert registro["fonte"] == "FNET"
    assert registro["ticker"] == "XPTO11"
    assert registro["status"] == "INDISPONIVEL"
    assert registro["score_confianca_fonte"] == 0.0
    assert registro["payload"]["fonte"] == "FNET"


def test_garantir_tabela_score_fontes_usa_create_aditivo(monkeypatch):
    sqls = []
    monkeypatch.setattr(score_fontes.db, "executar", lambda sql, params=(): sqls.append(sql))

    score_fontes.garantir_tabela_score_fontes()

    texto = "\n".join(sqls).upper()
    assert "CREATE TABLE IF NOT EXISTS GOVERNANCA_FONTES_SCORE_HISTORICO" in texto
    assert "CREATE INDEX IF NOT EXISTS" in texto
    assert "DROP" not in texto
    assert "ALTER TABLE" not in texto


def test_registrar_score_fonte_persistente_insere_campos_obrigatorios(monkeypatch):
    eventos = []
    chamadas_db = []
    monkeypatch.setattr(score_fontes.observabilidade, "registrar_evento", lambda *args, **kwargs: eventos.append({"args": args, "kwargs": kwargs}))
    monkeypatch.setattr(score_fontes, "garantir_tabela_score_fontes", lambda: None)
    monkeypatch.setattr(score_fontes.db, "executar", lambda sql, params=(): chamadas_db.append({"sql": sql, "params": params}))

    registro = score_fontes.registrar_score_fonte(
        fonte="BCB",
        ticker="MACRO",
        data_referencia="2026-05-19",
        status="VENCIDA",
        score=54.2,
        motivo="Série macro vencida.",
        payload={"serie": "CDI"},
        persistir=True,
    )

    assert registro["fonte"] == "BCB"
    assert chamadas_db
    params = chamadas_db[0]["params"]
    assert params[0] == "BCB"
    assert params[1] == "MACRO"
    assert params[2] == "2026-05-19"
    assert params[3] == "VENCIDA"
    assert params[4] == 54.2
    assert params[5] == "Série macro vencida."


def test_resumir_confiabilidade_fonte_sem_historico(monkeypatch):
    monkeypatch.setattr(score_fontes, "consultar_historico_fonte", lambda fonte, ticker=None, limite=100: [])

    resumo = score_fontes.resumir_confiabilidade_fonte("CVM", ticker="HGLG11")

    assert resumo["fonte"] == "CVM"
    assert resumo["ticker"] == "HGLG11"
    assert resumo["quantidade"] == 0
    assert resumo["score_medio"] is None
    assert resumo["uso"] == "AUDITORIA_APENAS"
    assert resumo["altera_decisao_automaticamente"] is False


def test_resumir_confiabilidade_fonte_com_historico(monkeypatch):
    historico = [
        {"fonte": "CVM", "ticker": "HGLG11", "data_referencia": "2026-05-19", "status": "OK", "score_confianca_fonte": 90.0},
        {"fonte": "CVM", "ticker": "HGLG11", "data_referencia": "2026-05-18", "status": "VENCIDA", "score_confianca_fonte": 50.0},
        {"fonte": "CVM", "ticker": "HGLG11", "data_referencia": "2026-05-17", "status": "OK", "score_confianca_fonte": 80.0},
    ]
    monkeypatch.setattr(score_fontes, "consultar_historico_fonte", lambda fonte, ticker=None, limite=100: historico)

    resumo = score_fontes.resumir_confiabilidade_fonte("CVM", ticker="HGLG11")

    assert resumo["quantidade"] == 3
    assert resumo["score_medio"] == 73.33
    assert resumo["ultimo_status"] == "OK"
    assert resumo["ultimo_score"] == 90.0
    assert resumo["status_distribuicao"] == {"OK": 2, "VENCIDA": 1}
    assert resumo["altera_decisao_automaticamente"] is False


def test_consultar_historico_fonte_monta_query_sem_rede(monkeypatch):
    chamadas = []
    monkeypatch.setattr(score_fontes, "garantir_tabela_score_fontes", lambda: None)
    monkeypatch.setattr(score_fontes.db, "buscar_todos", lambda sql, params=(): chamadas.append({"sql": sql, "params": params}) or [])

    resultado = score_fontes.consultar_historico_fonte("fundamentus", ticker="hglg11.sa", limite=10)

    assert resultado == []
    assert chamadas
    assert chamadas[0]["params"] == ("FUNDAMENTUS", "HGLG11", 10)
    assert "SELECT" in chamadas[0]["sql"].upper()
