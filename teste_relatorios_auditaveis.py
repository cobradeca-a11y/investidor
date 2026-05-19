"""
teste_relatorios_auditaveis.py

Valida relatórios técnicos auditáveis sem scraping, sem motor e sem alterar decisão.
"""
from __future__ import annotations

from relatorios import relatorios_auditaveis


def test_relatorio_decisoes_auditaveis_sem_replay_por_padrao(monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        relatorios_auditaveis,
        "listar_decisoes_auditaveis",
        lambda limite=50: {
            "status": "ok",
            "decisoes": [
                {
                    "id": 1,
                    "ticker": "HGLG11",
                    "data_decisao": "2026-05-19",
                    "decisao": "MONITORAR",
                    "payload_hash": "hash-salvo",
                    "contexto_versao": "asset-context-v1.3",
                    "versao_motor": "motor-v1",
                    "hash_valido": True,
                }
            ],
        },
    )

    def fake_consultar(decisao_id, incluir_payload=True, replay=False):
        chamadas.append({"decisao_id": decisao_id, "incluir_payload": incluir_payload, "replay": replay})
        return {
            "status": "ok",
            "decisao": {"id": decisao_id, "ticker": "HGLG11", "decisao": "MONITORAR", "contexto_versao": "asset-context-v1.3", "versao_motor": "motor-v1"},
            "auditoria": {"payload_hash_salvo": "hash-salvo", "payload_hash_calculado": "hash-salvo", "hash_valido": True},
            "payload": {"ticker": "HGLG11", "decisao": "MONITORAR", "gates_detalhes": {}},
            "replay": {"executado": False, "solicitado": False},
        }

    monkeypatch.setattr(relatorios_auditaveis, "consultar_decisao_auditavel", fake_consultar)

    relatorio = relatorios_auditaveis.gerar_relatorio_decisoes_auditaveis(limite=10)

    assert relatorio["status"] == "ok"
    assert relatorio["sem_scraping"] is True
    assert relatorio["executou_motor"] is False
    assert relatorio["alterou_decisao"] is False
    assert relatorio["incluir_replay"] is False
    assert chamadas == [{"decisao_id": 1, "incluir_payload": True, "replay": False}]
    assert relatorio["decisoes"][0]["contexto_versao"] == "asset-context-v1.3"
    assert relatorio["decisoes"][0]["versao_motor"] == "motor-v1"
    assert relatorio["decisoes"][0]["payload_hash"] == "hash-salvo"


def test_relatorio_decisoes_auditaveis_com_replay_explicito(monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        relatorios_auditaveis,
        "listar_decisoes_auditaveis",
        lambda limite=50: {"status": "ok", "decisoes": [{"id": 2, "ticker": "KNRI11", "decisao": "EVITAR"}]},
    )

    def fake_consultar(decisao_id, incluir_payload=True, replay=False):
        chamadas.append(replay)
        return {
            "status": "ok",
            "decisao": {"id": decisao_id, "ticker": "KNRI11", "decisao": "EVITAR"},
            "auditoria": {"payload_hash_salvo": "hash", "payload_hash_calculado": "hash", "hash_valido": True, "contexto_versao": "ctx", "versao_motor": "motor"},
            "payload": {"ticker": "KNRI11", "decisao": "EVITAR"},
            "replay": {"executado": True, "status": "ok", "replay_deterministico": True, "divergencia_replay": False, "payload_hash_salvo": "hash", "payload_hash_replay": "hash", "fonte_replay": "payload_json_persistido"},
        }

    monkeypatch.setattr(relatorios_auditaveis, "consultar_decisao_auditavel", fake_consultar)

    relatorio = relatorios_auditaveis.gerar_relatorio_decisoes_auditaveis(limite=10, incluir_replay=True)

    assert chamadas == [True]
    assert relatorio["incluir_replay"] is True
    assert relatorio["replays"][0]["executado"] is True
    assert relatorio["replays"][0]["divergencia_replay"] is False
    assert relatorio["replays"][0]["payload_hash_replay"] == "hash"


def test_relatorio_trata_dados_ausentes_com_nao_disponivel(monkeypatch):
    monkeypatch.setattr(
        relatorios_auditaveis,
        "listar_decisoes_auditaveis",
        lambda limite=50: {"status": "ok", "decisoes": [{"id": 3}]},
    )
    monkeypatch.setattr(
        relatorios_auditaveis,
        "consultar_decisao_auditavel",
        lambda decisao_id, incluir_payload=True, replay=False: {
            "status": "ok",
            "decisao": {"id": decisao_id},
            "auditoria": {},
            "payload": {},
            "replay": {},
        },
    )

    relatorio = relatorios_auditaveis.gerar_relatorio_decisoes_auditaveis()

    item = relatorio["decisoes"][0]
    assert item["ticker"] == "não disponível"
    assert item["data_decisao"] == "não disponível"
    assert item["versao_motor"] == "não disponível"
    assert item["contexto_versao"] == "não disponível"
    assert item["payload_hash"] == "não disponível"


def test_relatorio_extrai_bloqueios_fontes_e_gates(monkeypatch):
    monkeypatch.setattr(
        relatorios_auditaveis,
        "listar_decisoes_auditaveis",
        lambda limite=50: {"status": "ok", "decisoes": [{"id": 4, "ticker": "XPTO11", "decisao": "BLOQUEADO_DADOS_INSUFICIENTES"}]},
    )
    monkeypatch.setattr(
        relatorios_auditaveis,
        "consultar_decisao_auditavel",
        lambda decisao_id, incluir_payload=True, replay=False: {
            "status": "ok",
            "decisao": {"id": decisao_id, "ticker": "XPTO11", "decisao": "BLOQUEADO_DADOS_INSUFICIENTES"},
            "auditoria": {"payload_hash_salvo": "h", "payload_hash_calculado": "h", "hash_valido": True},
            "payload": {
                "ticker": "XPTO11",
                "decisao": "BLOQUEADO_DADOS_INSUFICIENTES",
                "permitir_decisao": False,
                "gate_parada": "G0",
                "motivo_bloqueio": "Dados mínimos ausentes.",
                "fonte_patrimonial": "CVM",
                "nivel_uso_dados": "ALTO",
                "score_confianca_dados": 90,
                "gates_detalhes": {
                    "0": {"gate": 0, "status": "BLOQUEADO", "aprovado": False, "eliminado": True, "motivos": ["sem dados"], "metricas": {"x": 1}, "fontes": ["contexto"], "penalidades": ["p1"]}
                },
            },
            "replay": {"executado": False},
        },
    )

    relatorio = relatorios_auditaveis.gerar_relatorio_decisoes_auditaveis()

    assert relatorio["bloqueios"]
    assert relatorio["bloqueios"][0]["gate_parada"] == "G0"
    assert relatorio["fontes"][0]["fonte_patrimonial"] == "CVM"
    assert relatorio["fontes"][0]["score_confianca_dados"] == 90
    assert relatorio["gates"][0]["status"] == "BLOQUEADO"
    assert relatorio["gates"][0]["fontes"] == ["contexto"]


def test_relatorio_carteira_auditavel_sem_scraping(monkeypatch):
    monkeypatch.setattr(
        relatorios_auditaveis.db,
        "buscar_todos",
        lambda sql: [
            {"ticker": "HGLG11", "quantidade": 10, "preco_medio": 150.0, "custo_total": 1500.0, "segmento": "Logístico", "atualizado_em": "2026-05-19"}
        ],
    )

    relatorio = relatorios_auditaveis.gerar_relatorio_carteira_auditavel()

    assert relatorio["status"] == "ok"
    assert relatorio["sem_scraping"] is True
    assert relatorio["executou_motor"] is False
    assert relatorio["alterou_decisao"] is False
    assert relatorio["posicoes"][0]["ticker"] == "HGLG11"


def test_relatorio_completo_e_markdown(monkeypatch):
    monkeypatch.setattr(
        relatorios_auditaveis,
        "gerar_relatorio_decisoes_auditaveis",
        lambda limite=50, incluir_replay=False: {
            "status": "ok",
            "tipo": "relatorio_auditavel",
            "decisoes": [{"id": 1, "ticker": "HGLG11", "data_decisao": "2026-05-19", "decisao": "MONITORAR", "contexto_versao": "ctx", "versao_motor": "motor", "payload_hash": "hash", "hash_valido": True}],
            "bloqueios": [],
            "replays": [{"decisao_id": 1, "ticker": "HGLG11", "executado": False, "status": "não disponível", "divergencia_replay": "não disponível"}],
        },
    )
    monkeypatch.setattr(
        relatorios_auditaveis,
        "gerar_relatorio_carteira_auditavel",
        lambda: {"status": "ok", "posicoes": []},
    )

    relatorio = relatorios_auditaveis.gerar_relatorio_auditavel_completo(limite=1)
    markdown = relatorios_auditaveis.gerar_markdown_relatorio_auditavel(relatorio)

    assert relatorio["status"] == "ok"
    assert relatorio["sem_scraping"] is True
    assert relatorio["executou_motor"] is False
    assert "# FIIA — Relatório Auditável" in markdown
    assert "HGLG11" in markdown
    assert "hash" in markdown


def test_relatorio_nao_chama_motor_ou_scraping(monkeypatch):
    monkeypatch.setattr(relatorios_auditaveis, "listar_decisoes_auditaveis", lambda limite=50: {"status": "ok", "decisoes": []})

    relatorio = relatorios_auditaveis.gerar_relatorio_decisoes_auditaveis()

    assert relatorio["sem_scraping"] is True
    assert relatorio["executou_motor"] is False
    assert relatorio["alterou_decisao"] is False
    assert relatorio["decisoes"] == []
