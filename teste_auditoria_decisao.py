"""
teste_auditoria_decisao.py

Valida a persistência auditável da decisão:
- payload_json normalizado;
- payload_hash SHA-256 estável;
- contexto_versao e versao_motor persistidos;
- reconstrução/validação sem coleta externa.
"""
from __future__ import annotations

import hashlib
import json

from decisao import persistencia_decisao as persistencia


def _payload_base() -> dict:
    return {
        "ticker": "HGLG11",
        "data_analise": "2026-05-18",
        "decisao": "MONITORAR",
        "motivo": "Teste auditável.",
        "confianca": "MEDIA",
        "risco": "MODERADO",
        "preco_atual": 160.0,
        "preco_justo": 170.0,
        "preco_entrada": 161.5,
        "margem": 6.25,
        "segmento": "LOGISTICA",
        "gate_parada": 7,
        "trilha_gates": ["Gate 0: APROVADO_DADOS"],
        "gates_detalhes": {
            "0": {
                "gate": 0,
                "status": "APROVADO_DADOS",
                "aprovado": True,
                "eliminado": False,
                "motivo": "Dados mínimos presentes.",
                "motivos": ["Dados mínimos presentes."],
                "metricas": {"semaforo": "VERDE"},
                "fontes": ["contexto"],
                "penalidades": [],
            }
        },
        "penalidades": [],
        "alertas": [],
        "dimensionamento": None,
        "zonas_entrada": None,
        "confianca_dados": {"score_global": 85, "nivel_uso": "USAR"},
        "versao_modelo": "2.1",
        "contexto_versao": "asset-context-v1.3",
        "contexto": {"contexto_versao": "asset-context-v1.3"},
    }


def test_campos_auditoria_sao_gerados_com_hash_estavel():
    dados = persistencia._normalizar_veredito(_payload_base())

    assert dados["payload_json"]
    assert dados["payload_hash"]
    assert dados["contexto_versao"] == "asset-context-v1.3"
    assert dados["versao_motor"] == "2.1"

    esperado = hashlib.sha256(dados["payload_json"].encode("utf-8")).hexdigest()
    assert dados["payload_hash"] == esperado

    # O JSON precisa ser parseável e canônico por ordenação estável.
    payload = json.loads(dados["payload_json"])
    assert payload["ticker"] == "HGLG11"
    assert payload["contexto_versao"] == "asset-context-v1.3"

    dados_reordenados = persistencia._normalizar_veredito(dict(reversed(list(_payload_base().items()))))
    assert dados_reordenados["payload_hash"] == dados["payload_hash"]


def test_validar_payload_salvo_confere_hash_e_reconstroi_payload():
    dados = persistencia._normalizar_veredito(_payload_base())

    resultado = persistencia.validar_payload_salvo(dados)

    assert resultado["valido"] is True
    assert resultado["payload_hash_salvo"] == dados["payload_hash"]
    assert resultado["payload_hash_calculado"] == dados["payload_hash"]
    assert resultado["payload"]["ticker"] == "HGLG11"
    assert resultado["contexto_versao"] == "asset-context-v1.3"
    assert resultado["versao_motor"] == "2.1"
    assert resultado["erro"] is None


def test_validar_payload_salvo_detecta_adulteracao():
    dados = persistencia._normalizar_veredito(_payload_base())
    dados_adulterados = dict(dados)
    payload = json.loads(dados_adulterados["payload_json"])
    payload["decisao"] = "COMPRAR"
    dados_adulterados["payload_json"] = persistencia._json_normalizado(payload)

    resultado = persistencia.validar_payload_salvo(dados_adulterados)

    assert resultado["valido"] is False
    assert resultado["payload_hash_salvo"] != resultado["payload_hash_calculado"]


def test_garantir_tabela_migracao_aditiva_inclui_colunas_auditoria(monkeypatch):
    colunas = ["id", "ticker", "data_decisao", "decisao", "payload_json"]
    comandos: list[str] = []

    def fake_buscar_todos(sql, params=()):
        if sql.startswith("PRAGMA table_info"):
            return [{"name": c} for c in colunas]
        return []

    def fake_executar(sql, params=()):
        comandos.append(sql)

    monkeypatch.setattr(persistencia.db, "buscar_todos", fake_buscar_todos)
    monkeypatch.setattr(persistencia.db, "executar", fake_executar)

    persistencia._garantir_tabela()

    sql_total = "\n".join(comandos).upper()
    assert "DROP" not in sql_total
    assert "ALTER TABLE DECISOES ADD COLUMN PAYLOAD_HASH" in sql_total
    assert "ALTER TABLE DECISOES ADD COLUMN CONTEXTO_VERSAO" in sql_total
    assert "ALTER TABLE DECISOES ADD COLUMN VERSAO_MOTOR" in sql_total
