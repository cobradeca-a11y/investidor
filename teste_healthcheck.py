"""
teste_healthcheck.py

Valida healthchecks e jobs operacionais sem scraping, sem motor e sem alterar decisão.
"""
from __future__ import annotations

from api import auditoria as api_auditoria
from operacional import healthcheck


def test_healthcheck_basico_nao_aciona_banco_fontes_ou_radar(monkeypatch):
    monkeypatch.setattr(healthcheck.observabilidade, "registrar_evento", lambda *args, **kwargs: None)
    monkeypatch.setattr(healthcheck, "verificar_banco_basico", lambda: (_ for _ in ()).throw(AssertionError("banco profundo não deve rodar")))
    monkeypatch.setattr(healthcheck, "verificar_fontes_criticas_sem_rede", lambda: (_ for _ in ()).throw(AssertionError("fontes não devem rodar")))
    monkeypatch.setattr(healthcheck, "verificar_radar_operacional", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("radar não deve rodar")))

    resposta = healthcheck.healthcheck_basico()

    assert resposta["nome"] == "healthcheck_basico"
    assert resposta["profundo"] is False
    assert resposta["sem_scraping"] is True
    assert resposta["executou_motor"] is False
    assert resposta["alterou_decisao"] is False
    componentes = {item["componente"] for item in resposta["componentes"]}
    assert "api" in componentes
    assert "configuracao" in componentes
    assert "observabilidade" in componentes
    assert "banco" not in componentes
    assert "fontes_criticas" not in componentes
    assert "radar" not in componentes


def test_healthcheck_profundo_e_explicito_sem_executar_radar(monkeypatch):
    monkeypatch.setattr(healthcheck.observabilidade, "registrar_evento", lambda *args, **kwargs: None)
    monkeypatch.setattr(healthcheck, "verificar_banco_basico", lambda: {"componente": "banco", "status": "OK", "motivo": "ok"})
    monkeypatch.setattr(healthcheck, "verificar_tabelas_minimas", lambda: {"componente": "banco_tabelas", "status": "OK", "motivo": "ok"})
    monkeypatch.setattr(healthcheck, "verificar_fontes_criticas_sem_rede", lambda: {"componente": "fontes_criticas", "status": "OK", "motivo": "sem rede", "fontes": []})

    resposta = healthcheck.healthcheck_profundo(incluir_radar=False)

    assert resposta["nome"] == "healthcheck_profundo"
    assert resposta["profundo"] is True
    assert resposta["radar_explicito_solicitado"] is False
    assert resposta["sem_scraping"] is True
    assert resposta["executou_motor"] is False
    radar = [item for item in resposta["componentes"] if item["componente"] == "radar"][0]
    assert radar["status"] == "NAO_EXECUTADO"
    assert radar["execucao_explicita_requerida"] is True


def test_verificar_radar_operacional_nao_executa_por_padrao():
    def executor():
        raise AssertionError("executor não deveria ser chamado")

    resposta = healthcheck.verificar_radar_operacional(executar=False, executor=executor)

    assert resposta["componente"] == "radar"
    assert resposta["status"] == "NAO_EXECUTADO"
    assert resposta["execucao_explicita_requerida"] is True


def test_verificar_radar_operacional_explicito_sem_executor_nao_chama_pipeline():
    resposta = healthcheck.verificar_radar_operacional(executar=True, executor=None)

    assert resposta["componente"] == "radar"
    assert resposta["status"] == "ALERTA"
    assert "nenhum executor" in resposta["motivo"].lower()


def test_verificar_banco_basico_sucesso(monkeypatch):
    monkeypatch.setattr(healthcheck.db, "buscar_um", lambda sql: {"ok": 1})

    resposta = healthcheck.verificar_banco_basico()

    assert resposta["componente"] == "banco"
    assert resposta["status"] == "OK"
    assert "SELECT 1" in resposta["motivo"]


def test_verificar_banco_basico_falha_sem_stacktrace(monkeypatch):
    def falhar(sql):
        raise RuntimeError("falha interna de teste")

    monkeypatch.setattr(healthcheck.db, "buscar_um", falhar)

    resposta = healthcheck.verificar_banco_basico()

    assert resposta["status"] == "ERRO"
    assert resposta["motivo"] == "Banco indisponível ou inacessível."
    assert resposta["tipo_erro"] == "RuntimeError"
    assert "traceback" not in str(resposta).lower()
    assert "falha interna de teste" not in str(resposta)


def test_verificar_fontes_criticas_sem_rede(monkeypatch):
    chamadas = []

    def fake_buscar_um(sql):
        chamadas.append(sql)
        return {"total": 0}

    monkeypatch.setattr(healthcheck.db, "buscar_um", fake_buscar_um)

    resposta = healthcheck.verificar_fontes_criticas_sem_rede()

    assert resposta["componente"] == "fontes_criticas"
    assert resposta["status"] == "ALERTA"
    assert resposta["motivo"] == "Fontes críticas verificadas por sinais locais, sem rede."
    assert len(resposta["fontes"]) == 5
    assert chamadas


def test_job_verificacao_operacional_registra_status(monkeypatch):
    eventos = []
    monkeypatch.setattr(healthcheck.observabilidade, "registrar_evento", lambda *args, **kwargs: eventos.append({"args": args, "kwargs": kwargs}))
    monkeypatch.setattr(healthcheck, "healthcheck_profundo", lambda incluir_radar=False: {"status": "OK", "componentes": [{"componente": "api", "status": "OK"}]})

    resposta = healthcheck.job_verificacao_operacional()

    assert resposta["job"] == "verificacao_operacional"
    assert resposta["status"] == "OK"
    assert "sem scraping" in resposta["motivo"]
    assert eventos


def test_api_health_basico_chama_healthcheck(monkeypatch):
    monkeypatch.setattr(api_auditoria.health_operacional, "healthcheck_basico", lambda: {"status": "OK", "nome": "healthcheck_basico"})

    resposta = api_auditoria.health_basico()

    assert resposta == {"status": "OK", "nome": "healthcheck_basico"}


def test_api_health_profundo_exige_autenticacao_no_router():
    rotas = {rota.path: rota for rota in api_auditoria.router.routes}
    assert "/api/auditoria/health" in rotas
    assert "/api/auditoria/health/profundo" in rotas
    assert "/api/auditoria/jobs/verificacao-operacional" in rotas

    for path in ["/api/auditoria/health/profundo", "/api/auditoria/jobs/verificacao-operacional"]:
        dependencias = [dep.dependency for dep in rotas[path].dependencies]
        assert api_auditoria.verificar_api_key in dependencias

    dependencias_basico = [dep.dependency for dep in rotas["/api/auditoria/health"].dependencies]
    assert api_auditoria.verificar_api_key not in dependencias_basico


def test_api_health_profundo_retorna_falha_controlada_sem_stacktrace(monkeypatch):
    def falhar(incluir_radar=False):
        raise RuntimeError("falha interna de teste")

    monkeypatch.setattr(api_auditoria.health_operacional, "healthcheck_profundo", falhar)
    monkeypatch.setattr(api_auditoria.observabilidade, "registrar_erro", lambda *args, **kwargs: None)

    resposta = api_auditoria.health_profundo(incluir_radar=True)

    assert resposta["status"] == "erro"
    assert "Falha controlada" in resposta["mensagem"]
    assert "traceback" not in str(resposta).lower()
    assert "falha interna de teste" not in str(resposta)
