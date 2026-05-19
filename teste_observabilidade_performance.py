"""
teste_observabilidade_performance.py

Valida observabilidade de performance sem quebrar Zero DB Query Mode:
- eventos estruturados em JSON;
- no-op quando observabilidade está desativada;
- métricas técnicas emitidas pelo Radar.
"""
from __future__ import annotations

import json

from processamento import estrategia
from sistema import observabilidade


def test_registrar_metrica_performance_emite_json_estruturado(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_path = log_dir / "fiia_eventos.jsonl"

    monkeypatch.setattr(observabilidade, "LOG_DIR", log_dir)
    monkeypatch.setattr(observabilidade, "LOG_PATH", log_path)
    observabilidade.configurar_observabilidade(True)

    observabilidade.registrar_metrica_performance(
        "processamento.estrategia",
        "radar_oportunidades",
        {
            "tempo_coleta_ms": 10.5,
            "tempo_decisao_ms": 2.0,
            "ativos_bloqueados": 1,
            "cache_hits": 3,
            "cache_misses": 2,
            "falhas_por_fonte": {"CVM": 1},
        },
    )

    linhas = log_path.read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 1

    evento = json.loads(linhas[0])
    assert evento["nivel"] == "METRIC"
    assert evento["modulo"] == "processamento.estrategia"
    assert evento["mensagem"] == "radar_oportunidades"
    assert evento["contexto"]["categoria"] == "performance"
    assert evento["contexto"]["metricas"]["cache_hits"] == 3
    assert evento["contexto"]["metricas"]["falhas_por_fonte"] == {"CVM": 1}


def test_observabilidade_noop_nao_cria_arquivo(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_path = log_dir / "fiia_eventos.jsonl"

    monkeypatch.setattr(observabilidade, "LOG_DIR", log_dir)
    monkeypatch.setattr(observabilidade, "LOG_PATH", log_path)
    observabilidade.configurar_observabilidade(False)

    observabilidade.registrar_metrica_performance(
        "teste",
        "noop",
        {"tempo_decisao_ms": 1},
    )

    assert not log_path.exists()
    observabilidade.configurar_observabilidade(True)


def test_resolver_contextos_ciclo_alimenta_metricas_cache(monkeypatch):
    chamadas: list[str] = []

    def fake_obter_contexto_ativo(ticker: str) -> dict:
        chamadas.append(ticker)
        return {
            "ticker": ticker,
            "contexto_versao": "asset-context-v1.3",
            "permitir_decisao": True,
        }

    metricas = {}
    monkeypatch.setattr("coleta.contexto_ativo.VERSAO_CONTEXTO", "asset-context-v1.3")
    monkeypatch.setattr("coleta.contexto_ativo.obter_contexto_ativo", fake_obter_contexto_ativo)

    resultado = estrategia._resolver_contextos_ciclo(["HGLG11", "hglg11.sa", "KNRI11"], metricas=metricas)

    assert sorted(resultado.keys()) == ["HGLG11", "KNRI11"]
    assert chamadas == ["HGLG11", "KNRI11"]
    assert metricas["cache_hits"] == 1
    assert metricas["cache_misses"] == 2
    assert metricas["contextos_regenerados"] == 0


def test_radar_emite_metricas_de_performance(monkeypatch):
    metricas_emitidas: list[dict] = []
    gravados: list[dict] = []

    mercado = [
        {"ticker": "BLOQ11", "segmento": "LOGISTICA", "liquidez": 2_000_000, "vacancia_media": 0.0},
        {"ticker": "OK11", "segmento": "LOGISTICA", "liquidez": 2_000_000, "vacancia_media": 0.0},
    ]

    def fake_obter_contexto_ativo(ticker: str) -> dict:
        if ticker == "BLOQ11":
            return {
                "ticker": ticker,
                "contexto_versao": "asset-context-v1.3",
                "permitir_decisao": False,
                "nivel_uso_dados": "INSUFICIENTE",
                "campos_ausentes": ["preco"],
                "campos_vencidos": [],
                "fontes_falharam": ["CVM"],
                "score_confianca": 20,
                "preco": None,
                "pvp": None,
                "vpa": None,
                "dy_12m": 0.0,
            }
        return {
            "ticker": ticker,
            "contexto_versao": "asset-context-v1.3",
            "permitir_decisao": True,
            "fontes_falharam": [],
        }

    def fake_decidir(ticker: str, score_ia=None, riscos_ia=None, tom_gestor=None, ia_status="INDISPONIVEL", contexto=None) -> dict:
        return {
            "ticker": ticker,
            "decisao": "COMPRAR" if ia_status == "OK" else "MONITORAR",
            "gate_parada": 7,
            "margem": 12.0,
            "fonte_patrimonial": "CVM_INF_MENSAL",
        }

    monkeypatch.setattr("coleta.api_fundamentus.coletar_mercado_inteiro", lambda: mercado)
    monkeypatch.setattr("coleta.contexto_ativo.VERSAO_CONTEXTO", "asset-context-v1.3")
    monkeypatch.setattr("coleta.contexto_ativo.obter_contexto_ativo", fake_obter_contexto_ativo)
    monkeypatch.setattr("processamento.analise_qualitativa.analisar_fundo_ia", lambda ticker: {"score": 8, "riscos": [], "tom_gestor": "neutro", "status": "OK"})
    monkeypatch.setattr("decisao.decisao_com_confianca.decidir", fake_decidir)
    monkeypatch.setattr("decisao.persistencia_decisao.gravar", lambda veredito: gravados.append(veredito) or 1)
    monkeypatch.setattr(estrategia.time, "sleep", lambda segundos: None)
    monkeypatch.setattr(
        "sistema.observabilidade.registrar_metrica_performance",
        lambda modulo, nome, metricas, ticker=None, fonte=None: metricas_emitidas.append(metricas),
    )

    resultado = estrategia.radar_oportunidades()

    assert len(resultado) == 2
    assert len(metricas_emitidas) == 1

    metricas = metricas_emitidas[0]
    assert metricas["ativos_mercado"] == 2
    assert metricas["ativos_sobreviventes"] == 2
    assert metricas["ativos_bloqueados"] == 1
    assert metricas["ativos_com_margem"] == 1
    assert metricas["ativos_finalistas"] == 2
    assert metricas["cache_misses"] == 2
    assert metricas["falhas_por_fonte"] == {"CVM": 1}
    assert "tempo_coleta_ms" in metricas
    assert "tempo_decisao_ms" in metricas
    assert "tempo_total_ms" in metricas
