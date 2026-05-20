from coleta import api_fundamentus
from processamento import estrategia


def test_fundamentus_busca_campos_com_rotulos_normalizados():
    dados = {
        "Vol $ méd (2m)": "1.234.567",
        "Patrim Líquido": "987.654.321",
        "Vacância Média": "4,2%",
        "Qtd imóveis": "12",
    }

    assert api_fundamentus._limpar_valor(api_fundamentus._campo_bruto(dados, "Vol $ med (2m)")) == 1234567.0
    assert api_fundamentus._limpar_valor(api_fundamentus._campo_bruto(dados, "Patrim Liquido")) == 987654321.0
    assert api_fundamentus._limpar_valor(api_fundamentus._campo_bruto(dados, "Vacancia Media")) == 4.2
    assert api_fundamentus._limpar_valor(api_fundamentus._campo_bruto(dados, "Qtd imoveis")) == 12.0


def test_hint_mercado_remove_bloqueio_de_liquidez_sem_mudar_threshold():
    contexto = {
        "ticker": "HGLG11",
        "contexto_versao": "asset-context-v1.3",
        "preco": 100.0,
        "vpa": 110.0,
        "pvp": 0.9,
        "liquidez_diaria": 0.0,
        "score_confianca": 70,
        "campos_ausentes": ["liquidez"],
        "permitir_decisao": False,
    }
    hint = {"liquidez": 2_000_000.0, "segmento": "LOGISTICA"}

    ajustado = estrategia._aplicar_hint_mercado_contexto(contexto, hint)

    assert ajustado["liquidez_diaria"] == 2_000_000.0
    assert ajustado["liquidez_fonte"] == "FundamentusMercado"
    assert "liquidez" not in ajustado["campos_ausentes"]
    assert ajustado["permitir_decisao"] is True


def test_card_bloqueado_carrega_auditoria_minima():
    contexto = {
        "ticker": "HSLG11",
        "contexto_versao": "asset-context-v1.3",
        "nivel_uso_dados": "INSUFICIENTE",
        "score_confianca": 30,
        "permitir_decisao": False,
        "patrimonio_fonte": "Fundamentus",
        "campos_ausentes": ["vpa"],
        "campos_vencidos": [],
        "fontes_falharam": ["CVM"],
    }

    card = estrategia._card_bloqueio_contexto("HSLG11", contexto)

    assert card["contexto_versao"] == "asset-context-v1.3"
    assert card["fonte_patrimonial"] == "Fundamentus"
    assert card["confianca_dados"]["score_global"] == 30
    assert card["gates_detalhes"]["0"]["status"] == "BLOQUEADO_DADOS_INSUFICIENTES"
    assert card["permitir_decisao"] is False

