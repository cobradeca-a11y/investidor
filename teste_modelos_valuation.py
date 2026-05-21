"""
Testes dos modelos concorrentes de valuation.

Os testes sao puros: nao acessam rede nem banco.
"""
from processamento.modelos_valuation import aplicar_modelos_valuation


def _contexto_base(**extra):
    contexto = {
        "ticker": "HGLG11",
        "data": "2022-05-20",
        "segmento": "LOGISTICA",
        "preco": 100.0,
        "vpa": 120.0,
        "dy_recorrente": 0.08,
        "ultimo_dividendo": 0.70,
        "cdi_atual": 0.10,
        "selic_atual": 0.12,
        "ipca_atual": 0.06,
        "patrimonio_fonte": "CVM_INF_MENSAL",
    }
    contexto.update(extra)
    return contexto


def _por_modelo(resultado, nome):
    return next(modelo for modelo in resultado["modelos"] if modelo["modelo"] == nome)


def test_modelo_bazin_barsi_fixo_calcula_preco_teto_por_dividendo():
    resultado = aplicar_modelos_valuation(_contexto_base())
    barsi = _por_modelo(resultado, "BAZIN_BARSI_6")

    assert barsi["aplicavel"] is True
    assert barsi["preco_justo"] == 133.33
    assert barsi["premissas"]["yield_exigido"] == 0.06


def test_modelo_bazin_barsi_cdi_exige_yield_dinamico():
    resultado = aplicar_modelos_valuation(_contexto_base(cdi_atual=0.12))
    barsi_cdi = _por_modelo(resultado, "BAZIN_BARSI_CDI")

    assert barsi_cdi["aplicavel"] is True
    assert barsi_cdi["premissas"]["yield_exigido"] == 0.13
    assert barsi_cdi["preco_justo"] == 61.54


def test_modelo_pvp_usa_vpa_sem_chamar_de_garantia():
    resultado = aplicar_modelos_valuation(_contexto_base())
    pvp = _por_modelo(resultado, "PVP_CVM")

    assert pvp["aplicavel"] is True
    assert pvp["preco_justo"] == 120.0
    assert pvp["premissas"]["fonte_patrimonial"] == "CVM_INF_MENSAL"


def test_composto_conservador_usa_menor_preco_aplicavel():
    resultado = aplicar_modelos_valuation(_contexto_base(cdi_atual=0.12))
    composto = resultado["composto_conservador"]

    assert composto["aplicavel"] is True
    assert composto["preco_justo"] == 61.54
    assert "BAZIN_BARSI_CDI" in composto["premissas"]["modelos_aplicaveis"]


def test_modelos_ficam_inaplicaveis_sem_preco_e_dividendo():
    resultado = aplicar_modelos_valuation(_contexto_base(preco=None, dy_recorrente=None, ultimo_dividendo=None))

    assert resultado["composto_conservador"]["aplicavel"] is True
    assert _por_modelo(resultado, "BAZIN_BARSI_6")["aplicavel"] is False
    assert _por_modelo(resultado, "GORDON_DDM")["aplicavel"] is False
    assert _por_modelo(resultado, "PVP_CVM")["aplicavel"] is True
