"""
teste_performance_radar.py

Valida otimizações do Radar sem alterar contratos decisórios:
- contexto é resolvido uma única vez por ticker no ciclo;
- cache do ciclo respeita VERSAO_CONTEXTO;
- contexto com versão diferente é obtido novamente;
- card bloqueado continua sendo retornado quando permitir_decisao=False.
"""
from __future__ import annotations

from processamento import estrategia


def test_resolver_contextos_ciclo_deduplica_tickers(monkeypatch):
    chamadas: list[str] = []

    def fake_obter_contexto_ativo(ticker: str) -> dict:
        chamadas.append(ticker)
        return {
            "ticker": ticker,
            "contexto_versao": "asset-context-v1.3",
            "permitir_decisao": True,
        }

    monkeypatch.setattr("coleta.contexto_ativo.VERSAO_CONTEXTO", "asset-context-v1.3")
    monkeypatch.setattr("coleta.contexto_ativo.obter_contexto_ativo", fake_obter_contexto_ativo)

    resultado = estrategia._resolver_contextos_ciclo(["HGLG11", "hglg11.sa", "KNRI11"])

    assert sorted(resultado.keys()) == ["HGLG11", "KNRI11"]
    assert chamadas == ["HGLG11", "KNRI11"]


def test_resolver_contextos_ciclo_rejeita_contexto_com_versao_errada(monkeypatch):
    chamadas: list[str] = []

    def fake_obter_contexto_ativo(ticker: str) -> dict:
        chamadas.append(ticker)
        if len(chamadas) == 1:
            return {
                "ticker": ticker,
                "contexto_versao": "asset-context-antigo",
                "permitir_decisao": True,
            }
        return {
            "ticker": ticker,
            "contexto_versao": "asset-context-v1.3",
            "permitir_decisao": True,
        }

    monkeypatch.setattr("coleta.contexto_ativo.VERSAO_CONTEXTO", "asset-context-v1.3")
    monkeypatch.setattr("coleta.contexto_ativo.obter_contexto_ativo", fake_obter_contexto_ativo)

    resultado = estrategia._resolver_contextos_ciclo(["HGLG11"])

    assert chamadas == ["HGLG11", "HGLG11"]
    assert resultado["HGLG11"]["contexto_versao"] == "asset-context-v1.3"


def test_card_bloqueio_contexto_preserva_motivo_e_campos():
    contexto = {
        "nivel_uso_dados": "INSUFICIENTE",
        "permitir_decisao": False,
        "campos_ausentes": ["preco", "vpa"],
        "campos_vencidos": ["liquidez"],
        "fontes_falharam": ["CVM"],
        "score_confianca": 25,
        "preco": None,
        "pvp": None,
        "vpa": None,
        "dy_12m": 0.0,
    }

    card = estrategia._card_bloqueio_contexto("HGLG11", contexto)

    assert card["ticker"] == "HGLG11"
    assert card["permitir_decisao"] is False
    assert card["decisao"] == "BLOQUEADO_DADOS_INSUFICIENTE"
    assert "preco" in card["motivo"]
    assert "vpa" in card["motivo"]
    assert card["gate_parada"] == 0
    assert card["trilha_gates"] == ["Gate 0: BLOQUEADO_DADOS_INSUFICIENTES"]


def test_radar_reaproveita_veredito_pre_ia_e_contexto(monkeypatch):
    chamadas_contexto: list[str] = []
    chamadas_decisao: list[tuple[str, str]] = []
    gravados: list[dict] = []

    mercado = [
        {"ticker": "HGLG11", "segmento": "LOGISTICA", "liquidez": 2_000_000, "vacancia_media": 0.0},
    ]
    contexto = {
        "ticker": "HGLG11",
        "contexto_versao": "asset-context-v1.3",
        "permitir_decisao": True,
    }

    def fake_obter_contexto_ativo(ticker: str) -> dict:
        chamadas_contexto.append(ticker)
        return contexto

    def fake_decidir(ticker: str, score_ia=None, riscos_ia=None, tom_gestor=None, ia_status="INDISPONIVEL", contexto=None) -> dict:
        chamadas_decisao.append((ticker, ia_status))
        return {
            "ticker": ticker,
            "decisao": "COMPRAR" if ia_status == "OK" else "MONITORAR",
            "gate_parada": 7,
            "margem": 10.0,
            "fonte_patrimonial": "CVM_INF_MENSAL",
        }

    monkeypatch.setattr("coleta.api_fundamentus.coletar_mercado_inteiro", lambda: mercado)
    monkeypatch.setattr("coleta.contexto_ativo.VERSAO_CONTEXTO", "asset-context-v1.3")
    monkeypatch.setattr("coleta.contexto_ativo.obter_contexto_ativo", fake_obter_contexto_ativo)
    monkeypatch.setattr("processamento.analise_qualitativa.analisar_fundo_ia", lambda ticker: {"score": 8, "riscos": [], "tom_gestor": "neutro", "status": "OK"})
    monkeypatch.setattr("decisao.decisao_com_confianca.decidir", fake_decidir)
    monkeypatch.setattr("decisao.persistencia_decisao.gravar", lambda veredito: gravados.append(veredito) or 1)
    monkeypatch.setattr(estrategia.time, "sleep", lambda segundos: None)

    resultado = estrategia.radar_oportunidades()

    assert chamadas_contexto == ["HGLG11"]
    assert chamadas_decisao == [("HGLG11", "INDISPONIVEL"), ("HGLG11", "OK")]
    assert len(gravados) == 1
    assert resultado[0]["veredito"]["decisao"] == "COMPRAR"


def test_radar_mantem_pre_veredito_quando_ia_falha(monkeypatch):
    gravados: list[dict] = []

    mercado = [
        {"ticker": "KORE11", "segmento": "OUTROS", "liquidez": 2_000_000, "vacancia_media": 0.0},
    ]
    contexto = {
        "ticker": "KORE11",
        "contexto_versao": "asset-context-v1.3",
        "permitir_decisao": True,
    }

    def fake_decidir(ticker: str, score_ia=None, riscos_ia=None, tom_gestor=None, ia_status="INDISPONIVEL", contexto=None) -> dict:
        return {
            "ticker": ticker,
            "decisao": "MONITORAR",
            "gate_parada": 7,
            "margem": 12.0,
            "fonte_patrimonial": "CVM_INF_MENSAL",
        }

    def falhar_ia(ticker: str) -> dict:
        raise RuntimeError("falha simulada na IA")

    monkeypatch.setattr("coleta.api_fundamentus.coletar_mercado_inteiro", lambda: mercado)
    monkeypatch.setattr("coleta.contexto_ativo.VERSAO_CONTEXTO", "asset-context-v1.3")
    monkeypatch.setattr("coleta.contexto_ativo.obter_contexto_ativo", lambda ticker: contexto)
    monkeypatch.setattr("processamento.analise_qualitativa.analisar_fundo_ia", falhar_ia)
    monkeypatch.setattr("decisao.decisao_com_confianca.decidir", fake_decidir)
    monkeypatch.setattr("decisao.persistencia_decisao.gravar", lambda veredito: gravados.append(veredito) or 1)
    monkeypatch.setattr(estrategia.time, "sleep", lambda segundos: None)

    resultado = estrategia.radar_oportunidades()

    veredito = resultado[0]["veredito"]
    assert veredito["ticker"] == "KORE11"
    assert veredito["ia_status"] == "ERRO_IA"
    assert veredito["score_ia"] == 0
    assert "falha simulada na IA" in veredito["alertas"][0]
    assert gravados[0]["ia_status"] == "ERRO_IA"
