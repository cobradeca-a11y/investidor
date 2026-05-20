"""
teste_precoleta_operacional.py

Valida a pre-coleta operacional explicita antes do Radar.
"""
from __future__ import annotations

from api import auditoria as api_auditoria
from operacional import healthcheck


def test_precoleta_nao_executa_por_padrao():
    def executor(_tickers):
        raise AssertionError("pre-coleta nao deve executar sem autorizacao explicita")

    resposta = healthcheck.executar_precoleta_operacional(
        executar=False,
        tickers=["hglg11"],
        executor=executor,
    )

    assert resposta["job"] == "precoleta_operacional"
    assert resposta["status"] == "NAO_EXECUTADO"
    assert resposta["tickers_solicitados"] == ["HGLG11"]
    assert resposta["sem_scraping"] is True
    assert resposta["executou_motor"] is False
    assert resposta["alterou_decisao"] is False


def test_precoleta_explicita_sem_executor_nao_chama_rede():
    resposta = healthcheck.executar_precoleta_operacional(
        executar=True,
        tickers=["kncr11"],
        executor=None,
    )

    assert resposta["status"] == "ALERTA"
    assert "executor autorizado" in resposta["motivo"]
    assert resposta["sem_scraping"] is True
    assert resposta["executou_motor"] is False
    assert resposta["alterou_decisao"] is False


def test_precoleta_explicita_usa_executor_autorizado():
    chamadas = []

    def executor(tickers):
        chamadas.append(tickers)
        return [{"ticker": ticker, "permitir_decisao": True} for ticker in tickers]

    resposta = healthcheck.executar_precoleta_operacional(
        executar=True,
        tickers=["hglg11", " kncr11 "],
        executor=executor,
    )

    assert chamadas == [["HGLG11", "KNCR11"]]
    assert resposta["status"] == "OK"
    assert resposta["tickers_processados"] == 2
    assert resposta["executou_motor"] is False
    assert resposta["alterou_decisao"] is False


def test_api_precoleta_exige_autenticacao_no_router():
    rotas = {rota.path: rota for rota in api_auditoria.router.routes}

    assert "/api/auditoria/jobs/precoleta-operacional" in rotas
    dependencias = [dep.dependency for dep in rotas["/api/auditoria/jobs/precoleta-operacional"].dependencies]
    assert api_auditoria.verificar_api_key in dependencias


def test_api_precoleta_sem_executar_nao_importa_coletor(monkeypatch):
    monkeypatch.setattr(api_auditoria.observabilidade, "registrar_erro", lambda *args, **kwargs: None)

    resposta = api_auditoria.job_precoleta_operacional(
        executar=False,
        tickers="hglg11,kncr11",
    )

    assert resposta["status"] == "ok"
    job = resposta["job"]
    assert job["status"] == "NAO_EXECUTADO"
    assert job["tickers_solicitados"] == ["HGLG11", "KNCR11"]
    assert job["sem_scraping"] is True
    assert job["executou_motor"] is False
    assert job["alterou_decisao"] is False
