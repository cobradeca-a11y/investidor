from decisao import auditoria_decisao
from decisao.objeto_decisao import normalizar_contrato_decisao
from decisao.persistencia_decisao import (
    VERSAO_MOTOR_DECISAO,
    _normalizar_veredito,
    _payload_de_json,
    _payload_hash,
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
    payload = _payload_de_json(dados["payload_json"])

    assert dados["payload_hash"] == _payload_hash(payload)
    assert dados["contexto_versao"] == "asset-context-test"
    assert dados["versao_motor"] == VERSAO_MOTOR_DECISAO


def test_replay_sem_drift(monkeypatch):
    payload = _payload_base()
    monkeypatch.setattr(
        auditoria_decisao,
        "reconstruir_payload_decisao",
        lambda decisao_id: {
            "decisao_id": decisao_id,
            "payload": payload,
            "payload_hash_original": _payload_hash(payload),
            "versao_motor": "fase3-contrato-v1",
        },
    )

    resultado = auditoria_decisao.auditar_replay_decisao(10, payload_recalculado=dict(payload))

    assert resultado["decisao_id"] == 10
    assert resultado["hash_confere"] is True
    assert resultado["campos_divergentes"] == []
    assert resultado["versao_motor_original"] == "fase3-contrato-v1"
    assert resultado["versao_motor_atual"] == VERSAO_MOTOR_DECISAO


def test_replay_detecta_drift(monkeypatch):
    payload = _payload_base()
    recalculado = dict(payload)
    recalculado["decisao"] = "AGUARDAR"
    recalculado["motivo"] = "Mudanca detectada."

    monkeypatch.setattr(
        auditoria_decisao,
        "reconstruir_payload_decisao",
        lambda decisao_id: {
            "decisao_id": decisao_id,
            "payload": payload,
            "payload_hash_original": _payload_hash(payload),
            "versao_motor": "fase3-contrato-v1",
        },
    )

    resultado = auditoria_decisao.auditar_replay_decisao(11, payload_recalculado=recalculado)

    assert resultado["hash_confere"] is False
    assert "decisao" in resultado["campos_divergentes"]
    assert "motivo" in resultado["campos_divergentes"]


def test_replay_aceita_reexecutor_injetado(monkeypatch):
    payload = _payload_base()
    monkeypatch.setattr(
        auditoria_decisao,
        "reconstruir_payload_decisao",
        lambda decisao_id: {
            "decisao_id": decisao_id,
            "payload": payload,
            "payload_hash_original": _payload_hash(payload),
            "versao_motor": "fase3-contrato-v1",
        },
    )

    resultado = auditoria_decisao.auditar_replay_decisao(12, reexecutar=lambda original: dict(original))

    assert resultado["hash_confere"] is True
    assert resultado["campos_divergentes"] == []
