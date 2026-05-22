from coleta.fnet_dividendos import _eh_metadado_provento, extrair_eventos_xml


XML_RENDIMENTO = b"""<?xml version="1.0"?>
<DadosEconomicoFinanceiros>
  <DadosGerais>
    <CNPJFundo>37087810000137</CNPJFundo>
    <DataInformacao>2023-08-07</DataInformacao>
  </DadosGerais>
  <InformeRendimentos>
    <Provento>
      <CodISIN>BRDEVACTF000</CodISIN>
      <CodNegociacao>DEVA11</CodNegociacao>
      <Rendimento>
        <AtoSocietarioAprovacao>07/08/2023</AtoSocietarioAprovacao>
        <DataBase>2023-08-07</DataBase>
        <ValorProvento>0.5</ValorProvento>
        <DataPagamento>2023-08-14</DataPagamento>
        <PeriodoReferencia>07-2023</PeriodoReferencia>
      </Rendimento>
    </Provento>
  </InformeRendimentos>
</DadosEconomicoFinanceiros>"""


XML_RENDIMENTO_AMORTIZACAO = b"""<?xml version="1.0"?>
<DadosEconomicoFinanceiros>
  <DadosGerais>
    <CNPJFundo>11111111000111</CNPJFundo>
    <DataInformacao>2024-01-10</DataInformacao>
  </DadosGerais>
  <InformeRendimentos>
    <Provento>
      <CodISIN>BRTESTCTF000</CodISIN>
      <CodNegociacao>TEST11</CodNegociacao>
      <Rendimento>
        <DataBase>2024-01-10</DataBase>
        <ValorProvento>0,80</ValorProvento>
        <DataPagamento>2024-01-17</DataPagamento>
      </Rendimento>
      <Amortizacao>
        <DataBase>2024-01-10</DataBase>
        <ValorProvento>0,20</ValorProvento>
        <DataPagamento>2024-01-17</DataPagamento>
      </Amortizacao>
    </Provento>
  </InformeRendimentos>
</DadosEconomicoFinanceiros>"""


def test_extrai_xml_fnet_rendimento():
    eventos = extrair_eventos_xml(XML_RENDIMENTO)

    assert eventos == [
        {
            "ticker": "DEVA11",
            "cnpj_fundo": "37087810000137",
            "data_base": "2023-08-07",
            "data_com": "2023-08-07",
            "data_pagamento": "2023-08-14",
            "valor": 0.5,
            "tipo": "RENDIMENTO",
            "cod_isin": "BRDEVACTF000",
            "periodo_referencia": "07-2023",
            "data_informacao": "2023-08-07",
            "ato_societario_aprovacao": "2023-08-07",
            "rendimento_isento_ir": None,
        }
    ]


def test_extrai_xml_fnet_preserva_eventos_separados():
    eventos = extrair_eventos_xml(XML_RENDIMENTO_AMORTIZACAO)

    assert [evento["tipo"] for evento in eventos] == ["RENDIMENTO", "AMORTIZACAO"]
    assert [evento["valor"] for evento in eventos] == [0.8, 0.2]
    assert all(evento["data_com"] == "2024-01-10" for evento in eventos)
    assert all(evento["data_pagamento"] == "2024-01-17" for evento in eventos)


def test_identifica_metadado_fnet_de_rendimentos_e_amortizacoes():
    assert _eh_metadado_provento(
        {
            "categoriaDocumento": "Aviso aos Cotistas - Estruturado",
            "tipoDocumento": "Rendimentos e Amortizações",
        }
    )
    assert not _eh_metadado_provento(
        {
            "categoriaDocumento": "Oferta Pública de Distribuição de Cotas",
            "tipoDocumento": "Anúncio de Início",
        }
    )
