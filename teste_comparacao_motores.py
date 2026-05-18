"""
teste_comparacao_motores.py
Valida a equivalência e compatibilidade entre o modo legado (SQLite) e o Zero DB Query Mode (contexto).
"""
import pytest

from coleta.contexto_ativo import obter_contexto_ativo
from decisao import motor_decisao_cvm_first


@pytest.mark.parametrize("ticker", ["HGLG11", "KNCR11", "CPTS11"])
def test_equivalencia_controlada_motores(ticker):
    """
    Compara a execução legacy vs contexto e assegura tolerância numérica <= 0.01
    para todas as métricas críticas calculadas de forma equivalente.
    """
    # 1. Resolve o contexto em memória
    contexto = obter_contexto_ativo(ticker)
    assert contexto is not None

    # 2. Executa no modo em memória (Zero DB)
    veredito_memoria = motor_decisao_cvm_first.decidir(
        ticker,
        score_ia=8.5,
        riscos_ia=["Concentração em ativos de qualidade"],
        tom_gestor="neutro",
        ia_status="OK",
        contexto=contexto
    )

    # 3. Executa no modo legado (consultando SQLite diretamente)
    veredito_legado = motor_decisao_cvm_first.decidir(
        ticker,
        score_ia=8.5,
        riscos_ia=["Concentração em ativos de qualidade"],
        tom_gestor="neutro",
        ia_status="OK",
        contexto=None
    )

    # 4. Assegura a equivalência controlada (tolerância <= 0.01 para floats)
    assert veredito_memoria["ticker"] == veredito_legado["ticker"]

    # Compara preços
    for campo in ["preco_atual", "preco_justo", "preco_entrada", "preco_stress"]:
        val_mem = veredito_memoria.get(campo)
        val_leg = veredito_legado.get(campo)
        if val_mem is not None and val_leg is not None:
            assert abs(val_mem - val_leg) <= 0.01, f"Diferença no campo {campo}: {val_mem} vs {val_leg} para {ticker}"

    # Compara indicadores e margens
    for campo in ["margem", "margem_stress", "pvp", "dy_12m_pct", "dy_recorrente_pct", "pct_recorrente", "premio_cdi"]:
        val_mem = veredito_memoria.get(campo)
        val_leg = veredito_legado.get(campo)
        if val_mem is not None and val_leg is not None:
            assert abs(val_mem - val_leg) <= 0.01, f"Diferença no campo {campo}: {val_mem} vs {val_leg} para {ticker}"


@pytest.mark.parametrize("ticker", ["HGLG11", "KNCR11", "CPTS11"])
def test_compatibilidade_real_motivos(ticker):
    """
    Assegura que os motivos da decisão no modo contexto são válidos,
    não vazios, sem tracebacks e estruturalmente consistentes.
    """
    contexto = obter_contexto_ativo(ticker)
    assert contexto is not None

    veredito = motor_decisao_cvm_first.decidir(
        ticker,
        score_ia=8.5,
        riscos_ia=["Concentração em ativos de qualidade"],
        tom_gestor="neutro",
        ia_status="OK",
        contexto=contexto
    )

    # 1. Assegura que a decisão e o motivo não estão vazios
    assert veredito["decisao"] is not None
    assert len(veredito["decisao"]) > 0
    assert veredito["motivo"] is not None
    assert len(veredito["motivo"].strip()) > 0

    # 2. Garante compatibilidade real: ausência de tracebacks ou palavras de erro técnico
    texto_motivo = veredito["motivo"].lower()
    assert "traceback" not in texto_motivo, "Detetado vazamento de traceback no motivo!"
    assert "error" not in texto_motivo, "Detetado erro técnico no motivo!"
    assert "exception" not in texto_motivo, "Detetada exceção interna no motivo!"

    # 3. Assegura que a decisão de confiança e revisão estão preenchidas
    assert veredito["confianca"] in ["ALTA", "MEDIA", "BAIXA"]
    assert len(veredito["revisao"].strip()) > 0

