from __future__ import annotations

from coleta.cnpj_fundo import _ticker_linha_mestre


def test_ticker_linha_mestre_prioriza_ticker_b3_11():
    row = {"ticker_b3_11": "KORE11", "ticker_base": "XXXX"}

    assert _ticker_linha_mestre(row) == "KORE11"


def test_ticker_linha_mestre_monta_ticker_por_base_quando_preciso():
    row = {"ticker_base": "KORE"}

    assert _ticker_linha_mestre(row) == "KORE11"


def test_ticker_linha_mestre_nao_cria_ticker_11_sem_base():
    assert _ticker_linha_mestre({}) == ""
