"""
teste_aprovacao_ajustes.py

Valida fluxo de feedback humano para sugestões de ajuste sem alterar motor.
"""
from __future__ import annotations

from aprendizado import ajustes_pesos
from api import aprendizado as api_aprendizado


def test_criar_sugestao_nasce_pendente(monkeypatch):
    monkeypatch.setattr(ajustes_pesos.observabilidade, "registrar_evento", lambda *args, **kwargs: None)
    monkeypatch.setattr(ajustes_pesos.db, "executar", lambda *args, **kwargs: None)
    monkeypatch.setattr(ajustes_pesos, "garantir_tabela_sugestoes_ajuste", lambda: None)

    sugestao = ajustes_pesos.criar_sugestao_ajuste(
        regra="acao=COMPRAR|janela=90",
        tipo_sugestao="REDUZIR_PESO",
        peso_atual=20.0,
        peso_sugerido=15.0,
        evidencia={"fp_pct": 40.0},
        amostra=50,
        periodo_inicio="2026-01-01",
        periodo_fim="2026-05-01",
        impacto_estimado="Reduzir falsos positivos.",
        motivo="Falsos positivos acima do esperado.",
        persistir=False,
    )

    assert sugestao["estado"] == "PENDENTE"
    assert sugestao["usuario_decisao"] is None
    assert sugestao["origem_decisao"] is None
    assert sugestao["decidido_em"] is None
    assert sugestao["justificativa_decisao"] is None
    assert sugestao["aplicado"] is False
    assert sugestao["aplica_automaticamente"] is False


def test_garantir_tabela_sugestoes_tem_colunas_de_aprovacao(monkeypatch):
    sqls = []
    monkeypatch.setattr(ajustes_pesos.db, "buscar_todos", lambda *args, **kwargs: [])
    monkeypatch.setattr(ajustes_pesos.db, "executar", lambda sql, params=(): sqls.append(sql))

    ajustes_pesos.garantir_tabela_sugestoes_ajuste()

    texto = "\n".join(sqls).upper()
    assert "CREATE TABLE IF NOT EXISTS APRENDIZADO_SUGESTOES_AJUSTE_PESOS" in texto
    assert "ESTADO" in texto
    assert "PENDENTE" in texto
    assert "APROVADA" in texto
    assert "REJEITADA" in texto
    assert "EXPIRADA" in texto
    assert "USUARIO_DECISAO" in texto
    assert "ORIGEM_DECISAO" in texto
    assert "JUSTIFICATIVA_DECISAO" in texto
    assert "DROP" not in texto


def test_aprovar_sugestao_registra_feedback_sem_alterar_motor(monkeypatch):
    chamadas = []
    eventos = []
    sugestao = {"id": 1, "estado": "PENDENTE", "regra": "acao=COMPRAR|janela=90"}

    monkeypatch.setattr(ajustes_pesos, "garantir_tabela_sugestoes_ajuste", lambda: None)
    monkeypatch.setattr(ajustes_pesos, "obter_sugestao", lambda sugestao_id: sugestao)
    monkeypatch.setattr(ajustes_pesos.db, "executar", lambda sql, params=(): chamadas.append({"sql": sql, "params": params}))
    monkeypatch.setattr(ajustes_pesos.observabilidade, "registrar_evento", lambda *args, **kwargs: eventos.append({"args": args, "kwargs": kwargs}))

    resultado = ajustes_pesos.aprovar_sugestao(
        1,
        usuario="andre",
        origem="API_TESTE",
        justificativa="Amostra suficiente para revisão manual.",
    )

    assert resultado["status"] == "ok"
    assert resultado["estado"] == "APROVADA"
    assert resultado["usuario_decisao"] == "andre"
    assert resultado["origem_decisao"] == "API_TESTE"
    assert resultado["justificativa_decisao"] == "Amostra suficiente para revisão manual."
    assert resultado["alterou_motor"] is False
    assert resultado["aplicado"] is False
    assert chamadas
    assert chamadas[0]["params"][0] == "APROVADA"
    assert chamadas[0]["params"][1] == "andre"
    assert chamadas[0]["params"][2] == "API_TESTE"
    assert chamadas[0]["params"][4] == "Amostra suficiente para revisão manual."
    assert eventos


def test_rejeitar_sugestao_registra_feedback():
    chamadas = []
    ajustes_pesos.garantir_tabela_sugestoes_ajuste = lambda: None
    ajustes_pesos.obter_sugestao = lambda sugestao_id: {"id": sugestao_id, "estado": "PENDENTE"}
    ajustes_pesos.db.executar = lambda sql, params=(): chamadas.append({"sql": sql, "params": params})
    ajustes_pesos.observabilidade.registrar_evento = lambda *args, **kwargs: None

    resultado = ajustes_pesos.rejeitar_sugestao(2, usuario="andre", origem="TESTE", justificativa="Evidência insuficiente.")

    assert resultado["estado"] == "REJEITADA"
    assert resultado["alterou_motor"] is False
    assert resultado["aplicado"] is False
    assert chamadas[0]["params"][0] == "REJEITADA"


def test_expirar_sugestao_registra_feedback():
    chamadas = []
    ajustes_pesos.garantir_tabela_sugestoes_ajuste = lambda: None
    ajustes_pesos.obter_sugestao = lambda sugestao_id: {"id": sugestao_id, "estado": "PENDENTE"}
    ajustes_pesos.db.executar = lambda sql, params=(): chamadas.append({"sql": sql, "params": params})
    ajustes_pesos.observabilidade.registrar_evento = lambda *args, **kwargs: None

    resultado = ajustes_pesos.expirar_sugestao(3, usuario="sistema", origem="ROTINA", justificativa="Sugestão antiga.")

    assert resultado["estado"] == "EXPIRADA"
    assert resultado["alterou_motor"] is False
    assert resultado["aplicado"] is False
    assert chamadas[0]["params"][0] == "EXPIRADA"


def test_sugestao_nao_pendente_nao_muda_estado(monkeypatch):
    chamadas = []
    monkeypatch.setattr(ajustes_pesos, "garantir_tabela_sugestoes_ajuste", lambda: None)
    monkeypatch.setattr(ajustes_pesos, "obter_sugestao", lambda sugestao_id: {"id": sugestao_id, "estado": "APROVADA"})
    monkeypatch.setattr(ajustes_pesos.db, "executar", lambda *args, **kwargs: chamadas.append(args))

    resultado = ajustes_pesos.rejeitar_sugestao(4, usuario="andre", origem="TESTE", justificativa="Tentativa inválida.")

    assert resultado["status"] == "bloqueado"
    assert resultado["estado_atual"] == "APROVADA"
    assert resultado["alterou_motor"] is False
    assert resultado["aplicado"] is False
    assert chamadas == []


def test_sugestao_inexistente_retorna_nao_encontrada(monkeypatch):
    monkeypatch.setattr(ajustes_pesos, "garantir_tabela_sugestoes_ajuste", lambda: None)
    monkeypatch.setattr(ajustes_pesos, "obter_sugestao", lambda sugestao_id: None)

    resultado = ajustes_pesos.aprovar_sugestao(999, usuario="andre", origem="TESTE", justificativa="n/a")

    assert resultado["status"] == "nao_encontrada"
    assert resultado["alterou_motor"] is False
    assert resultado["aplicado"] is False


def test_endpoints_de_aprovacao_exigem_autenticacao():
    rotas = {
        rota.path: rota
        for rota in api_aprendizado.router.routes
        if getattr(rota, "path", "").startswith("/api/aprendizado/ajustes")
    }

    assert "/api/aprendizado/ajustes" in rotas
    assert "/api/aprendizado/ajustes/{sugestao_id}/aprovar" in rotas
    assert "/api/aprendizado/ajustes/{sugestao_id}/rejeitar" in rotas
    assert "/api/aprendizado/ajustes/{sugestao_id}/expirar" in rotas

    for path, rota in rotas.items():
        dependencias = [dep.dependency for dep in rota.dependencies]
        assert api_aprendizado.verificar_api_key in dependencias, path


def test_api_aprovar_usa_fluxo_sem_scraping(monkeypatch):
    chamadas = []
    payload = api_aprendizado.DecisaoAjusteRequest(
        usuario="andre",
        origem="TESTE_API",
        justificativa="Aprovação manual controlada.",
    )
    monkeypatch.setattr(
        api_aprendizado.ajustes_pesos,
        "aprovar_sugestao",
        lambda sugestao_id, usuario, origem, justificativa: chamadas.append({
            "sugestao_id": sugestao_id,
            "usuario": usuario,
            "origem": origem,
            "justificativa": justificativa,
        }) or {"status": "ok", "estado": "APROVADA", "alterou_motor": False, "aplicado": False},
    )

    resposta = api_aprendizado.aprovar_ajuste(7, payload)

    assert resposta["status"] == "ok"
    assert resposta["estado"] == "APROVADA"
    assert resposta["alterou_motor"] is False
    assert resposta["aplicado"] is False
    assert chamadas == [{
        "sugestao_id": 7,
        "usuario": "andre",
        "origem": "TESTE_API",
        "justificativa": "Aprovação manual controlada.",
    }]
