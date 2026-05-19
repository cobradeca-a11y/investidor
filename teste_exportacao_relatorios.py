"""
teste_exportacao_relatorios.py

Valida exportação CSV/JSON de relatórios auditáveis.
"""
from __future__ import annotations

from fastapi import Response

from api import relatorios as api_relatorios
from relatorios import exportacao_relatorios


def _relatorio_fake():
    return {
        "status": "ok",
        "tipo": "relatorio_auditavel_completo",
        "versao_relatorio": "relatorio-auditavel-v1",
        "gerado_em": "2026-05-19T00:00:00+00:00",
        "sem_scraping": True,
        "executou_motor": False,
        "alterou_decisao": False,
        "carteira": {"resumo": {"quantidade_posicoes": 1}, "posicoes": []},
        "decisoes": {
            "status": "ok",
            "tipo": "relatorio_auditavel",
            "resumo": {
                "quantidade_decisoes": 1,
                "quantidade_bloqueios": 1,
                "quantidade_fontes": 1,
                "quantidade_gates": 1,
                "quantidade_replays": 1,
            },
            "decisoes": [
                {
                    "id": 1,
                    "ticker": "HGLG11",
                    "data_decisao": "2026-05-19",
                    "decisao": "MONITORAR",
                    "motivo": "Teste",
                    "confianca": "MEDIA",
                    "risco": "MODERADO",
                    "score_final": 70,
                    "contexto_versao": "asset-context-v1.3",
                    "versao_motor": "motor-v1",
                    "payload_hash": "hash",
                    "hash_valido": True,
                    "api_key": "nao_exportar",
                    "token": "nao_exportar",
                }
            ],
            "fontes": [
                {
                    "ticker": "HGLG11",
                    "fonte_patrimonial": "CVM",
                    "nivel_uso_dados": "ALTO",
                    "score_confianca_dados": 90,
                    "contexto_versao": "asset-context-v1.3",
                    "versao_motor": "motor-v1",
                    "payload_hash": "hash",
                    "secret": "nao_exportar",
                }
            ],
            "bloqueios": [
                {
                    "ticker": "HGLG11",
                    "tipo": "campos_ausentes",
                    "decisao": "MONITORAR",
                    "gate_parada": "G0",
                    "motivo": "Campo ausente",
                }
            ],
            "replays": [
                {
                    "decisao_id": 1,
                    "ticker": "HGLG11",
                    "solicitado": True,
                    "executado": True,
                    "status": "ok",
                    "replay_deterministico": True,
                    "divergencia_replay": False,
                    "payload_hash_salvo": "hash",
                    "payload_hash_replay": "hash",
                    "fonte_replay": "payload_json_persistido",
                }
            ],
        },
    }


def test_exportacao_json_decisoes_campos_estaveis_sem_sensiveis(monkeypatch):
    monkeypatch.setattr(exportacao_relatorios, "gerar_relatorio_auditavel_completo", lambda limite=50, incluir_replay=False: _relatorio_fake())

    exportacao = exportacao_relatorios.gerar_exportacao_json(secao="decisoes", limite=10)

    assert exportacao["status"] == "ok"
    assert exportacao["formato"] == "json"
    assert exportacao["campos"] == exportacao_relatorios.CAMPOS_DECISOES
    assert exportacao["sem_scraping"] is True
    assert exportacao["executou_motor"] is False
    assert exportacao["alterou_decisao"] is False
    assert exportacao["dados_sensiveis_exportados"] is False
    assert set(exportacao["dados"][0].keys()) == set(exportacao_relatorios.CAMPOS_DECISOES)
    texto = str(exportacao)
    assert "nao_exportar" not in texto
    assert "api_key" not in texto.lower()
    assert "token" not in texto.lower()


def test_exportacao_csv_decisoes_tem_cabecalho_estavel(monkeypatch):
    monkeypatch.setattr(exportacao_relatorios, "gerar_relatorio_auditavel_completo", lambda limite=50, incluir_replay=False: _relatorio_fake())

    exportacao = exportacao_relatorios.gerar_exportacao_csv(secao="decisoes", limite=10)

    assert exportacao["status"] == "ok"
    assert exportacao["formato"] == "csv"
    primeira_linha = exportacao["conteudo"].splitlines()[0]
    assert primeira_linha == ",".join(exportacao_relatorios.CAMPOS_DECISOES)
    assert "HGLG11" in exportacao["conteudo"]
    assert "nao_exportar" not in exportacao["conteudo"]


def test_exportacao_secao_metricas(monkeypatch):
    monkeypatch.setattr(exportacao_relatorios, "gerar_relatorio_auditavel_completo", lambda limite=50, incluir_replay=False: _relatorio_fake())

    exportacao = exportacao_relatorios.gerar_exportacao_json(secao="metricas")

    assert exportacao["status"] == "ok"
    assert exportacao["campos"] == exportacao_relatorios.CAMPOS_METRICAS
    assert exportacao["dados"][0]["quantidade_decisoes"] == 1
    assert exportacao["dados"][0]["quantidade_posicoes"] == 1
    assert exportacao["dados"][0]["sem_scraping"] is True


def test_exportacao_replay_explicitamente(monkeypatch):
    chamadas = []

    def fake_relatorio(limite=50, incluir_replay=False):
        chamadas.append(incluir_replay)
        return _relatorio_fake()

    monkeypatch.setattr(exportacao_relatorios, "gerar_relatorio_auditavel_completo", fake_relatorio)

    exportacao = exportacao_relatorios.gerar_exportacao_json(secao="replay", incluir_replay=True)

    assert chamadas == [True]
    assert exportacao["status"] == "ok"
    assert exportacao["campos"] == exportacao_relatorios.CAMPOS_REPLAY
    assert exportacao["dados"][0]["executado"] is True


def test_exportacao_secao_invalida():
    exportacao = exportacao_relatorios.gerar_exportacao_json(secao="segredos")

    assert exportacao["status"] == "erro"
    assert "secoes_validas" in exportacao


def test_exportacao_formato_invalido():
    exportacao = exportacao_relatorios.gerar_exportacao(formato="xlsx")

    assert exportacao["status"] == "erro"
    assert exportacao["formatos_validos"] == ["csv", "json"]


def test_api_exportacao_json(monkeypatch):
    monkeypatch.setattr(
        api_relatorios,
        "gerar_exportacao",
        lambda formato="json", secao="decisoes", limite=50, incluir_replay=False: {
            "status": "ok",
            "formato": "json",
            "secao": secao,
            "dados": [],
            "campos": [],
        },
    )

    resposta = api_relatorios.exportar_relatorio(formato="json", secao="decisoes")

    assert isinstance(resposta, dict)
    assert resposta["status"] == "ok"
    assert resposta["formato"] == "json"


def test_api_exportacao_csv(monkeypatch):
    monkeypatch.setattr(
        api_relatorios,
        "gerar_exportacao",
        lambda formato="csv", secao="decisoes", limite=50, incluir_replay=False: {
            "status": "ok",
            "formato": "csv",
            "secao": secao,
            "conteudo": "id,ticker\n1,HGLG11\n",
        },
    )

    resposta = api_relatorios.exportar_relatorio(formato="csv", secao="decisoes")

    assert isinstance(resposta, Response)
    assert resposta.media_type.startswith("text/csv")
    assert b"HGLG11" in resposta.body
    assert "attachment" in resposta.headers.get("content-disposition", "")


def test_endpoints_relatorios_exigem_autenticacao():
    rotas = {
        rota.path: rota
        for rota in api_relatorios.router.routes
        if getattr(rota, "path", "").startswith("/api/relatorios")
    }

    esperadas = {
        "/api/relatorios/completo",
        "/api/relatorios/markdown",
        "/api/relatorios/ativo/{ticker}",
        "/api/relatorios/comparar",
        "/api/relatorios/exportar",
    }
    assert esperadas.issubset(set(rotas))
    for path in esperadas:
        dependencias = [dep.dependency for dep in rotas[path].dependencies]
        assert api_relatorios.verificar_api_key in dependencias, path
