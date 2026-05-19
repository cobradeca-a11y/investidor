"""
teste_aprendizado_operacional.py

Valida aprendizado operacional sem alterar decisão, motor ou thresholds.
"""
from __future__ import annotations

import pytest

from aprendizado import resultados, ajustes_pesos
from config import settings


def test_janelas_avaliacao_suportadas():
    assert settings.JANELAS_AVALIACAO_DIAS == [30, 90, 180, 365]
    for janela in [30, 90, 180, 365]:
        assert resultados.validar_janela(janela) == janela

    with pytest.raises(ValueError):
        resultados.validar_janela(45)


def test_classificar_falso_positivo():
    classificado = resultados.classificar_resultado_operacional(
        acao_original="COMPRAR",
        retorno_total_pct=2.0,
        benchmark_pct=8.0,
    )

    assert classificado["resultado"] == "FALSO_POSITIVO"
    assert classificado["falso_positivo"] is True
    assert classificado["falso_negativo"] is False
    assert classificado["superou_benchmark"] is False


def test_classificar_falso_negativo():
    classificado = resultados.classificar_resultado_operacional(
        acao_original="EVITAR",
        retorno_total_pct=14.0,
        benchmark_pct=7.0,
    )

    assert classificado["resultado"] == "FALSO_NEGATIVO"
    assert classificado["falso_positivo"] is False
    assert classificado["falso_negativo"] is True
    assert classificado["superou_benchmark"] is True


def test_avaliar_resultado_temporal_sem_persistencia(monkeypatch):
    eventos = []
    monkeypatch.setattr(resultados.observabilidade, "registrar_evento", lambda *args, **kwargs: eventos.append({"args": args, "kwargs": kwargs}))
    monkeypatch.setattr(resultados.db, "executar", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("não deveria persistir")))

    registro = resultados.avaliar_resultado_temporal(
        ticker="hglg11.sa",
        acao_original="COMPRAR",
        data_decisao="2026-01-01",
        data_avaliacao="2026-04-01",
        janela_dias=90,
        preco_entrada=100.0,
        preco_saida=110.0,
        dividendos_pct=2.0,
        benchmark_pct=8.0,
        evidencia={"origem": "teste"},
        persistir=False,
    )

    assert registro["ticker"] == "HGLG11"
    assert registro["janela_dias"] == 90
    assert registro["retorno_preco_pct"] == 10.0
    assert registro["retorno_total_pct"] == 12.0
    assert registro["resultado"] == "ACERTO"
    assert registro["evidencia"]["origem"] == "teste"
    assert eventos


def test_garantir_tabela_resultados_operacionais_aditiva(monkeypatch):
    sqls = []
    monkeypatch.setattr(resultados.db, "executar", lambda sql, params=(): sqls.append(sql))

    resultados.garantir_tabela_resultados_operacionais()

    texto = "\n".join(sqls).upper()
    assert "CREATE TABLE IF NOT EXISTS APRENDIZADO_RESULTADOS_OPERACIONAIS" in texto
    assert "CREATE INDEX IF NOT EXISTS" in texto
    assert "DROP" not in texto


def test_criar_sugestao_controlada_sem_persistencia(monkeypatch):
    eventos = []
    monkeypatch.setattr(ajustes_pesos.observabilidade, "registrar_evento", lambda *args, **kwargs: eventos.append({"args": args, "kwargs": kwargs}))
    monkeypatch.setattr(ajustes_pesos.db, "executar", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("não deveria persistir")))

    sugestao = ajustes_pesos.criar_sugestao_ajuste(
        regra="acao=COMPRAR|janela=90",
        tipo_sugestao="REDUZIR_PESO",
        peso_atual=20.0,
        peso_sugerido=15.0,
        evidencia={"falsos_positivos_pct": 42.0},
        amostra=50,
        periodo_inicio="2026-01-01",
        periodo_fim="2026-05-01",
        impacto_estimado="Reduzir falsos positivos.",
        motivo="Falsos positivos acima do limite.",
        persistir=False,
    )

    assert sugestao["tipo_sugestao"] == "REDUZIR_PESO"
    assert sugestao["amostra"] == 50
    assert sugestao["periodo_inicio"] == "2026-01-01"
    assert sugestao["periodo_fim"] == "2026-05-01"
    assert sugestao["impacto_estimado"] == "Reduzir falsos positivos."
    assert sugestao["aplicado"] is False
    assert sugestao["requer_aprovacao_humana"] is True
    assert sugestao["aplica_automaticamente"] is False
    assert eventos


def test_garantir_tabela_sugestoes_ajuste_aditiva(monkeypatch):
    sqls = []
    monkeypatch.setattr(ajustes_pesos.db, "executar", lambda sql, params=(): sqls.append(sql))

    ajustes_pesos.garantir_tabela_sugestoes_ajuste()

    texto = "\n".join(sqls).upper()
    assert "CREATE TABLE IF NOT EXISTS APRENDIZADO_SUGESTOES_AJUSTE_PESOS" in texto
    assert "REQUIRE" not in texto
    assert "DROP" not in texto
    assert "CREATE INDEX IF NOT EXISTS" in texto


def test_aplicar_sugestao_automaticamente_bloqueado():
    resposta = ajustes_pesos.aplicar_sugestao_automaticamente(id=1)

    assert resposta["status"] == "bloqueado"
    assert resposta["aplicado"] is False
    assert "aprovação humana" in resposta["motivo"]


def test_detectar_padroes_e_gerar_sugestoes(monkeypatch):
    rows = []
    for i in range(6):
        rows.append({
            "acao_original": "COMPRAR",
            "janela_dias": 90,
            "falso_positivo": 1 if i < 3 else 0,
            "falso_negativo": 0,
            "data_decisao": f"2026-01-{i+1:02d}",
            "data_avaliacao": f"2026-04-{i+1:02d}",
        })
    monkeypatch.setattr(ajustes_pesos, "garantir_tabela_resultados_operacionais", lambda: None)
    monkeypatch.setattr(ajustes_pesos.db, "buscar_todos", lambda sql, params=(): rows)
    monkeypatch.setattr(ajustes_pesos.observabilidade, "registrar_evento", lambda *args, **kwargs: None)

    padroes = ajustes_pesos.detectar_padroes_de_erro(min_amostras=5, janela_dias=90)
    sugestoes = ajustes_pesos.gerar_sugestoes_controladas(min_amostras=5, janela_dias=90, persistir=False)

    assert len(padroes) == 1
    assert padroes[0]["amostra"] == 6
    assert padroes[0]["falsos_positivos_pct"] == 50.0
    assert len(sugestoes) == 1
    assert sugestoes[0]["tipo_sugestao"] == "REDUZIR_PESO"
    assert sugestoes[0]["aplicado"] is False


def test_sugestao_persistente_contem_campos_obrigatorios(monkeypatch):
    chamadas = []
    monkeypatch.setattr(ajustes_pesos, "garantir_tabela_sugestoes_ajuste", lambda: None)
    monkeypatch.setattr(ajustes_pesos.observabilidade, "registrar_evento", lambda *args, **kwargs: None)
    monkeypatch.setattr(ajustes_pesos.db, "executar", lambda sql, params=(): chamadas.append({"sql": sql, "params": params}))

    ajustes_pesos.criar_sugestao_ajuste(
        regra="acao=EVITAR|janela=365",
        tipo_sugestao="AUMENTAR_PESO",
        peso_atual=None,
        peso_sugerido=None,
        evidencia={"falsos_negativos_pct": 40.0},
        amostra=80,
        periodo_inicio="2025-01-01",
        periodo_fim="2026-01-01",
        impacto_estimado="Reduzir falsos negativos.",
        motivo="Ativos evitados superaram benchmark.",
        persistir=True,
    )

    assert chamadas
    params = chamadas[0]["params"]
    assert params[0] == "acao=EVITAR|janela=365"
    assert params[1] == "AUMENTAR_PESO"
    assert params[5] == 80
    assert params[8] == "Reduzir falsos negativos."
    assert params[9] == "Ativos evitados superaram benchmark."
    assert params[10] == 0
    assert params[11] == 1
