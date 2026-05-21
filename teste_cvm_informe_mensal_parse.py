"""
teste_cvm_informe_mensal_parse.py

Regressao para parsing do arquivo complemento do informe mensal CVM.
"""
from __future__ import annotations

import pandas as pd

from coleta import cvm_informe_mensal
from coleta import tabela_mestre_fiis


def test_tabela_mestre_reconhece_ticker_b3_11():
    df = pd.DataFrame({"ticker_b3_11": ["HGLG11"], "cnpj_fundo": ["11.728.688/0001-47"]})

    assert tabela_mestre_fiis._localizar(df, "ticker") == "ticker_b3_11"


def test_to_float_preserva_decimal_com_ponto_e_converte_formato_br():
    assert cvm_informe_mensal._to_float("166.408892") == 166.408892
    assert cvm_informe_mensal._to_float("7056514999.0") == 7056514999.0
    assert cvm_informe_mensal._to_float("1.234,56") == 1234.56


def test_extrair_registros_do_complemento_cvm_com_campos_patrimoniais():
    df = pd.DataFrame(
        [
            {
                "CNPJ_Fundo_Classe": "11.728.688/0001-47",
                "Data_Referencia": "2026-04-01",
                "Patrimonio_Liquido": "7056514999.0",
                "Valor_Patrimonial_Cotas": "166.408892",
                "Total_Numero_Cotistas": "536031.0",
                "Cotas_Emitidas": "42404675.0",
            }
        ]
    )

    registros = cvm_informe_mensal._extrair_registros(
        2026,
        "inf_mensal_fii_complemento_2026.csv",
        df,
    )

    assert len(registros) == 1
    registro = registros[0]
    assert registro["cnpj_fundo"] == "11.728.688/0001-47"
    assert registro["competencia"] == "2026-04-01"
    assert registro["patrimonio_liquido"] == 7056514999.0
    assert registro["valor_patrimonial_cota"] == 166.408892
    assert registro["num_cotistas"] == 536031
    assert registro["num_cotas"] == 42404675.0


def test_ultimo_por_cnpj_prioriza_registro_com_vp_cota(monkeypatch):
    consultas = []

    monkeypatch.setattr(cvm_informe_mensal, "garantir_tabela", lambda: None)

    def fake_buscar_um(sql, params):
        consultas.append(sql)
        return {
            "cnpj_fundo": params[0],
            "competencia": "2026-04-01",
            "valor_patrimonial_cota": 166.40,
        }

    monkeypatch.setattr(cvm_informe_mensal.db, "buscar_um", fake_buscar_um)

    resposta = cvm_informe_mensal.ultimo_por_cnpj("11.728.688/0001-47")

    assert resposta["valor_patrimonial_cota"] == 166.40
    assert "CASE WHEN valor_patrimonial_cota IS NOT NULL" in consultas[0]


def test_tabela_mestre_importa_csv_com_bom(tmp_path):
    bom = b"\xef\xbb\xbf"
    arquivo = tmp_path / "tabela_teste.csv"
    arquivo.write_bytes(
        bom + b"ticker_b3_11;cnpj_fundo\n"
        b"HGLG11;11.728.688/0001-47\n"
        b"KNCR11;08.181.530/0001-74\n"
    )

    resultado = tabela_mestre_fiis.importar_csv(arquivo)

    assert resultado.get("registros", 0) == 2
    assert "erro" not in resultado
