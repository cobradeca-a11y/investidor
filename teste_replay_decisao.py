from decisao import auditoria_decisao
from decisao.objeto_decisao import normalizar_contrato_decisao
from decisao.persistencia_decisao import (
    _normalizar_veredito,
    _hash_payload_json,
    validar_payload_salvo,
)


def _payload_base():
    contexto = {
        "ticker": "HGLG11",
        "contexto_versao": "asset-context-test",
        "preco": 100.0,
        "segmento": "LOGISTICA",
    }
    return normalizar_contrato_decisao(
        {
            "ticker": "HGLG11",
            "data_analise": "2026-05-18",
            "decisao": "MONITORAR",
            "motivo": "Replay deterministico.",
            "confianca": "MEDIA",
            "preco_atual": 100.0,
            "preco_justo": 110.0,
            "preco_entrada": 104.5,
            "preco_teto": 104.5,
            "margem": 10.0,
            "trilha_gates": ["Gate 0: APROVADO_DADOS"],
            "gates_detalhes": {
                "0": {
                    "gate": 0,
                    "status": "APROVADO_DADOS",
                    "aprovado": True,
                    "eliminado": False,
                    "motivo": "Dados presentes.",
                    "motivos": ["Dados presentes."],
                    "metricas": {},
                    "fontes": [],
                    "penalidades": [],
                }
            },
            "contexto": contexto,
        },
        contexto,
    )


def test_persistencia_salva_hash_auditavel():
    dados = _normalizar_veredito(_payload_base())
    validacao = validar_payload_salvo(dados)

    assert validacao["valido"] is True
    assert dados["payload_hash"] == _hash_payload_json(dados["payload_json"])
    assert dados["contexto_versao"] == "asset-context-test"
    assert dados["versao_motor"]


def test_consulta_auditavel_sem_replay(monkeypatch):
    dados = _normalizar_veredito(_payload_base())
    dados["id"] = 10

    monkeypatch.setattr(auditoria_decisao, "buscar_decisao_salva", lambda decisao_id: dados)

    resultado = auditoria_decisao.consultar_decisao_auditavel(10, incluir_payload=True, replay=False)

    assert resultado["status"] == "ok"
    assert resultado["decisao"]["id"] == 10
    assert resultado["auditoria"]["hash_valido"] is True
    assert resultado["replay"]["executado"] is False
    assert resultado["payload"]["ticker"] == "HGLG11"


def test_consulta_auditavel_com_replay(monkeypatch):
    dados = _normalizar_veredito(_payload_base())
    dados["id"] = 11

    monkeypatch.setattr(auditoria_decisao, "buscar_decisao_salva", lambda decisao_id: dados)
    monkeypatch.setattr(
        auditoria_decisao,
        "replay_decisao_salva",
        lambda decisao_id: {
            "status": "ok",
            "payload_hash_salvo": dados["payload_hash"],
            "payload_hash_replay": dados["payload_hash"],
            "replay_deterministico": True,
            "fonte_replay": "payload_json_persistido",
        },
    )

    resultado = auditoria_decisao.consultar_decisao_auditavel(11, incluir_payload=False, replay=True)

    assert resultado["status"] == "ok"
    assert resultado["replay"]["executado"] is True
    assert resultado["replay"]["replay_deterministico"] is True
    assert resultado["replay"]["divergencia_replay"] is False


def test_consulta_auditavel_nao_encontrada(monkeypatch):
    monkeypatch.setattr(auditoria_decisao, "buscar_decisao_salva", lambda decisao_id: None)

    resultado = auditoria_decisao.consultar_decisao_auditavel(999)

    assert resultado["status"] == "nao_encontrado"
    assert resultado["decisao_id"] == 999
