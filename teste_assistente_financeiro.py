from __future__ import annotations

from servicos import assistente_financeiro as af
import servicos.agendador as agendador


def test_alerta_zona_entrada_e_dividendo_ausente(monkeypatch):
    salvos: list[dict] = []

    monkeypatch.setattr(af.db, "executar", lambda *args, **kwargs: None)
    monkeypatch.setattr(af, "_salvar_alerta", lambda alerta: salvos.append(alerta))
    monkeypatch.setattr(af, "_ultimo_indicador", lambda ticker: {"ticker": ticker, "preco": 90.0})
    monkeypatch.setattr(af, "_ultimo_dividendo", lambda ticker: None)
    monkeypatch.setattr(af, "_ultimo_trimestral", lambda ticker: {"data_referencia": "2026-03-31"})
    monkeypatch.setattr(af, "ultima_decisao", lambda ticker: {"ticker": ticker, "decisao": "COMPRAR_PARCIAL", "preco_entrada": 95.0})

    resultado = af.gerar_alertas(["KORE11"])

    tipos = {item["tipo"] for item in resultado["alertas"]}
    assert "ZONA_ENTRADA" in tipos
    assert "DIVIDENDO_AUSENTE" in tipos
    assert len(salvos) == resultado["quantidade"]


def test_listar_alertas_novos_nao_gera_alertas(monkeypatch):
    monkeypatch.setattr(af, "gerar_alertas", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("nao deve gerar")))
    monkeypatch.setattr(af, "_garantir_tabela_alertas", lambda: None)
    monkeypatch.setattr(
        af.db,
        "buscar_todos",
        lambda *args, **kwargs: [
            {
                "id": 12,
                "ticker": "KORE11",
                "tipo": "ZONA_ENTRADA",
                "severidade": "ALTA",
                "mensagem": "KORE11 entrou na zona.",
                "data_referencia": "2026-05-21",
                "payload_json": '{"preco": 90}',
                "criado_em": "2026-05-21T12:00:00+00:00",
            }
        ],
    )

    resultado = af.listar_alertas_novos(desde_id=10)

    assert resultado["gerou_alertas"] is False
    assert resultado["quantidade"] == 1
    assert resultado["ultimo_id"] == 12
    assert resultado["alertas"][0]["payload"]["preco"] == 90


def test_evolucao_classifica_melhora_por_confiabilidade(monkeypatch):
    monkeypatch.setattr(
        af,
        "_ultimo_indicador",
        lambda ticker: {"ticker": ticker, "data": "2026-05-20", "confiabilidade": 90, "vacancia_fisica": 5.0},
    )
    monkeypatch.setattr(
        af,
        "_indicador_anterior",
        lambda ticker, data: {"ticker": ticker, "data": "2026-04-20", "confiabilidade": 70, "vacancia_fisica": 5.0},
    )
    monkeypatch.setattr(af, "historico", lambda ticker, limite=2: [{"decisao": "MONITORAR"}, {"decisao": "MONITORAR"}])

    resultado = af.evolucao_fundo("HGLG11")

    assert resultado["leitura"] == "MELHOROU"
    assert resultado["metricas"]["confiabilidade"]["delta"] == 20.0


def test_rebalanceamento_usa_politica_carteira(monkeypatch):
    monkeypatch.setattr(
        af.repositorio_carteira,
        "listar_posicoes",
        lambda: [{"ticker": "HGLG11", "quantidade": 10, "preco_medio": 100.0, "segmento": "LOGISTICA"}],
    )
    monkeypatch.setattr(af, "_ultimo_indicador", lambda ticker: {"preco": 110.0, "segmento": "LOGISTICA"})
    monkeypatch.setattr(af, "ultima_decisao", lambda ticker: {"ticker": ticker, "decisao": "MANTER", "confianca": "MEDIA"})

    resultado = af.rebalanceamento()

    assert resultado["quantidade"] == 1
    assert resultado["valor_total_estimado"] == 1100.0
    assert resultado["sugestoes"][0]["politica"]["acao_carteira"] == "BLOQUEAR_APORTE"
    assert resultado["sugestoes"][0]["politica"]["travas"]


def test_relatorio_offline_texto(monkeypatch):
    monkeypatch.setattr(
        af,
        "detalhe_fundo",
        lambda ticker: {
            "ticker": "HGLG11",
            "indicador": {"preco": 100, "pvp": 0.9, "dy_12m": 0.1},
            "decisao": {"decisao": "MANTER", "confianca": "MEDIA", "motivo": "Teste"},
            "trimestral": {"vacancia_media_ponderada": 3.0, "quantidade_imoveis": 5},
            "ultimo_dividendo": {"valor": 0.8, "data_pagamento": "2026-05-15"},
            "fnet": {"quantidade_documentos": 2, "tipos": ["INFORME_MENSAL"]},
        },
    )
    monkeypatch.setattr(af, "evolucao_fundo", lambda ticker: {"leitura": "ESTAVEL"})
    monkeypatch.setattr(af, "gerar_alertas", lambda tickers: {"alertas": []})

    resultado = af.relatorio_offline("HGLG11")

    assert resultado["status"] == "ok"
    assert "FIIA - Relatorio offline: HGLG11" in resultado["conteudo"]
    assert "Sem alertas operacionais" in resultado["conteudo"]


def test_lista_alertas_novos_sem_gerar_novos_alertas(monkeypatch):
    monkeypatch.setattr(af, "_garantir_tabela_alertas", lambda: None)
    monkeypatch.setattr(
        af.db,
        "buscar_todos",
        lambda sql, params=(): [
            {
                "id": 7,
                "ticker": "HGLG11",
                "tipo": "ZONA_ENTRADA",
                "severidade": "ALTA",
                "mensagem": "Entrou na zona de entrada.",
                "data_referencia": "2026-05-21",
                "payload_json": '{"preco": 90}',
                "criado_em": "2026-05-21T10:00:00+00:00",
            }
        ],
    )

    resultado = af.listar_alertas_novos(desde_id=3)

    assert resultado["quantidade"] == 1
    assert resultado["ultimo_id"] == 7
    assert resultado["alertas"][0]["payload"]["preco"] == 90


def test_relatorio_offline_pdf(monkeypatch):
    monkeypatch.setattr(
        af,
        "detalhe_fundo",
        lambda ticker: {
            "ticker": "HGLG11",
            "indicador": {"preco": 100, "pvp": 0.9, "dy_12m": 0.1},
            "decisao": {"decisao": "MANTER", "confianca": "MEDIA", "motivo": "Teste"},
            "trimestral": {"vacancia_media_ponderada": 3.0, "quantidade_imoveis": 5},
            "ultimo_dividendo": {"valor": 0.8, "data_pagamento": "2026-05-15"},
            "fnet": {"quantidade_documentos": 2, "tipos": ["INFORME_MENSAL"]},
        },
    )
    monkeypatch.setattr(af, "evolucao_fundo", lambda ticker: {"leitura": "ESTAVEL"})
    monkeypatch.setattr(af, "gerar_alertas", lambda tickers: {"alertas": []})

    resultado = af.relatorio_offline("HGLG11", formato="pdf")

    assert resultado["formato"] == "pdf"
    assert resultado["content_type"] == "application/pdf"
    assert resultado["conteudo"].startswith(b"%PDF-")


def test_agendador_dispara_gerar_alertas(monkeypatch):
    chamadas = []

    monkeypatch.setattr(agendador, "gerar_alertas", lambda: chamadas.append(True) or {"quantidade": 3})

    agendador.rotina_alertas_assistente()

    assert chamadas == [True]
