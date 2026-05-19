from decisao.motor_decisao import _gate_result, _gate0_validacao, _gate6_qualitativo, decidir
from coleta.contexto_ativo import obter_contexto_ativo

def test_contrato_minimo_gates():
    res = _gate_result(0, "APROVADO_DADOS", "Motivo generico")
    
    assert "gate" in res
    assert "status" in res
    assert "aprovado" in res
    assert "eliminado" in res
    assert "motivos" in res
    assert "metricas" in res
    assert "fontes" in res
    assert "penalidades" in res
    
    assert res["aprovado"] is True
    assert res["eliminado"] is False
    assert isinstance(res["motivos"], list)
    assert isinstance(res["metricas"], dict)
    assert isinstance(res["fontes"], list)
    assert isinstance(res["penalidades"], list)

def test_contrato_gate_eliminado():
    res = _gate_result(1, "ELIMINADO_LIQUIDEZ", "Motivo")
    assert res["aprovado"] is False
    assert res["eliminado"] is True

def test_contrato_na_pratica_gate0():
    res = _gate0_validacao("TEST11", {"preco": 100.0, "pvp": 1.0, "liquidez_diaria": 2000000, "vpa": 100.0, "dy_12m": 0.1}, {"segmento": "LOGISTICA"})
    assert "aprovado" in res
    assert "motivos" in res
    assert "metricas" in res
    assert "fontes" in res

def test_veto_qualitativo_semantica_aprovado():
    res = _gate6_qualitativo(score_ia=3, riscos_ia=["Risco grave de execucao"], tom_gestor="pessimista", ia_status="OK")
    assert res["status"] == "VETO_QUALITATIVO"
    assert res["aprovado"] is False
    assert res["eliminado"] is False

def test_decidir_gates_detalhes_contrato_completo():
    ticker = "HGLG11"
    contexto = obter_contexto_ativo(ticker)
    
    veredito = decidir(ticker, score_ia=8.5, riscos_ia=[], tom_gestor="neutro", ia_status="OK", contexto=contexto)
    
    assert "gates_detalhes" in veredito
    detalhes = veredito["gates_detalhes"]
    
    # Verifica pelo menos um gate (ex: gate 0 ou 1)
    # Tem que ter todas as chaves do contrato novo
    for g_id, g_data in detalhes.items():
        assert "gate" in g_data
        assert "status" in g_data
        assert "aprovado" in g_data
        assert "eliminado" in g_data
        assert "motivos" in g_data
        assert "metricas" in g_data
        assert "fontes" in g_data
        assert "penalidades" in g_data
