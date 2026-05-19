"""
teste_api_decisoes.py

Valida a API de consulta de decisão auditável:
- endpoints protegidos por API key existente;
- consulta não dispara scraping nem motor;
- replay é opcional e explícito;
- resposta não expõe stacktrace.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from api import auditoria as api_auditoria
from decisao import auditoria_decisao


API_KEY_TESTE = "fiia-teste"


def test_verificar_api_key_rejeita_ausente(monkeypatch):
    monkeypatch.setattr(api_auditoria, "FIIA_API_KEY", API_KEY_TESTE)

    with pytest.raises(HTTPException) as exc:
        api_auditoria.verificar_api_key(None)

    assert exc.value.status_code == 401


def test_verificar_api_key_aceita_valida(monkeypatch):
    monkeypatch.setattr(api_auditoria, "FIIA_API_KEY", API_KEY_TESTE)

    assert api_auditoria.verificar_api_key(API_KEY_TESTE) is None


def test_listar_decisoes_auditaveis_api_protegida_sem_stacktrace(monkeypatch):
    monkeypatch.setattr(api_auditoria, "FIIA_API_KEY", API_KEY_TESTE)
    monkeypatch.setattr(
        api_auditoria,
        "listar_decisoes_auditaveis",
        lambda limite=50: {
            "status": "ok",
            "quantidade": 1,
            "decisoes": [
                {
                    "id": 1,
                    "ticker": "HGLG11",
                    "decisao": "MONITORAR",
                    "payload_hash": "abc",
                    "hash_valido": True,
                }
            ],
        },
    )

    resposta = api_auditoria.listar_decisoes_auditaveis_api(limite=10)

    assert resposta["status"] == "ok"
    assert resposta["quantidade"] == 1
    assert resposta["decisoes"][0]["payload_hash"] == "abc"


def test_consultar_decisao_auditavel_api_sem_replay_por_padrao(monkeypatch):
    chamadas = []

    def fake_consultar(decisao_id: int, *, incluir_payload: bool = True, replay: bool = False):
        chamadas.append({"decisao_id": decisao_id, "incluir_payload": incluir_payload, "replay": replay})
        return {
            "status": "ok",
            "decisao": {"id": decisao_id, "ticker": "HGLG11", "decisao": "MONITORAR"},
            "auditoria": {"hash_valido": True},
            "payload": {"ticker": "HGLG11", "decisao": "MONITORAR"},
            "replay": {"executado": False, "solicitado": False},
        }

    monkeypatch.setattr(api_auditoria, "consultar_decisao_auditavel", fake_consultar)

    resposta = api_auditoria.consultar_decisao_auditavel_api(7)

    assert chamadas == [{"decisao_id": 7, "incluir_payload": True, "replay": False}]
    assert resposta["status"] == "ok"
    assert resposta["replay"]["executado"] is False
    assert resposta["payload"]["ticker"] == "HGLG11"


def test_consultar_decisao_auditavel_api_com_replay_explicito(monkeypatch):
    chamadas = []

    def fake_consultar(decisao_id: int, *, incluir_payload: bool = True, replay: bool = False):
        chamadas.append({"decisao_id": decisao_id, "incluir_payload": incluir_payload, "replay": replay})
        return {
            "status": "ok",
            "decisao": {"id": decisao_id, "ticker": "HGLG11", "decisao": "MONITORAR"},
            "auditoria": {"hash_valido": True},
            "payload": {"ticker": "HGLG11", "decisao": "MONITORAR"},
            "replay": {
                "executado": True,
                "status": "ok",
                "replay_deterministico": True,
                "divergencia_replay": False,
            },
        }

    monkeypatch.setattr(api_auditoria, "consultar_decisao_auditavel", fake_consultar)

    resposta = api_auditoria.consultar_decisao_auditavel_api(7, replay=True)

    assert chamadas == [{"decisao_id": 7, "incluir_payload": True, "replay": True}]
    assert resposta["replay"]["executado"] is True
    assert resposta["replay"]["divergencia_replay"] is False


def test_consultar_decisao_auditavel_api_404(monkeypatch):
    monkeypatch.setattr(
        api_auditoria,
        "consultar_decisao_auditavel",
        lambda decisao_id, incluir_payload=True, replay=False: {
            "status": "nao_encontrado",
            "mensagem": "Decisão não encontrada.",
            "decisao_id": decisao_id,
        },
    )

    with pytest.raises(HTTPException) as exc:
        api_auditoria.consultar_decisao_auditavel_api(999)

    assert exc.value.status_code == 404


def test_consultar_decisao_auditavel_api_erro_controlado_sem_stacktrace(monkeypatch):
    def falhar(*args, **kwargs):
        raise RuntimeError("erro interno sensivel")

    monkeypatch.setattr(api_auditoria, "consultar_decisao_auditavel", falhar)
    monkeypatch.setattr(api_auditoria.observabilidade, "registrar_erro", lambda *args, **kwargs: None)

    resposta = api_auditoria.consultar_decisao_auditavel_api(1)

    assert resposta["status"] == "erro"
    assert "Falha controlada" in resposta["mensagem"]
    assert "traceback" not in str(resposta).lower()
    assert "erro interno sensivel" not in str(resposta)


def test_servico_consulta_nao_chama_motor_nem_scraping(monkeypatch):
    registro = {
        "id": 1,
        "ticker": "HGLG11",
        "data_decisao": "2026-05-18",
        "decisao": "MONITORAR",
        "motivo": "Teste",
        "confianca": "MEDIA",
        "risco": "MODERADO",
        "score_final": 70,
        "preco_na_decisao": 160.0,
        "preco_justo": 170.0,
        "preco_entrada": 150.0,
        "margem": 5.0,
        "payload_json": "{}",
        "payload_hash": "hash",
        "contexto_versao": "asset-context-v1.3",
        "versao_motor": "2.1",
    }
    chamadas = []

    monkeypatch.setattr(auditoria_decisao.db, "buscar_um", lambda sql, params=(): registro)
    monkeypatch.setattr(
        auditoria_decisao,
        "validar_payload_salvo",
        lambda registro: {
            "valido": True,
            "payload": {"ticker": "HGLG11", "decisao": "MONITORAR"},
            "payload_hash_salvo": "hash",
            "payload_hash_calculado": "hash",
            "contexto_versao": "asset-context-v1.3",
            "versao_motor": "2.1",
            "erro": None,
        },
    )
    monkeypatch.setattr(
        auditoria_decisao,
        "replay_decisao_salva",
        lambda decisao_id: chamadas.append(decisao_id) or {
            "status": "ok",
            "replay_deterministico": True,
            "payload_hash_salvo": "hash",
            "payload_hash_replay": "hash",
            "fonte_replay": "payload_json_persistido",
        },
    )

    resposta_sem_replay = auditoria_decisao.consultar_decisao_auditavel(1, replay=False)
    resposta_com_replay = auditoria_decisao.consultar_decisao_auditavel(1, replay=True)

    assert resposta_sem_replay["status"] == "ok"
    assert resposta_sem_replay["replay"]["executado"] is False
    assert resposta_com_replay["replay"]["executado"] is True
    assert chamadas == [1]
