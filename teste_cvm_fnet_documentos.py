from __future__ import annotations

from coleta import cvm_fnet_documentos as fnet


def test_normalizar_documento_aceita_payload_da_api_fnet():
    doc = fnet._normalizar_documento(
        {
            "id": 123,
            "descricaoFundo": "KINEA OPORTUNIDADES",
            "tipoDocumento": "Informe Mensal",
            "dataReferencia": "2026-04-01",
            "dataEntrega": "2026-05-15",
            "codSegNegociacao": "KORE11",
            "cnpjFundo": "52.219.978/0001-42",
        },
        arquivo_origem="TESTE",
        coletado_em="2026-05-20T00:00:00+00:00",
    )

    assert doc["ticker"] == "KORE11"
    assert doc["cnpj_fundo"] == "52.219.978/0001-42"
    assert doc["tipo_documento"] == "Informe Mensal"
    assert doc["protocolo"] == "123"
    assert doc["dedupe_key"]


def test_importar_registros_contabiliza_sem_banco_real(monkeypatch):
    chamados = []

    def fake_registrar(item, arquivo_origem="FNET_API"):
        chamados.append((item, arquivo_origem))
        return {"status": "ok"}

    monkeypatch.setattr(fnet, "registrar_documento", fake_registrar)
    monkeypatch.setattr(fnet.observabilidade, "registrar_evento", lambda *args, **kwargs: None)

    resumo = fnet.importar_registros([{"ticker": "KORE11"}, {"ticker": "HGLG11"}], arquivo_origem="TESTE")

    assert resumo["registros"] == 2
    assert resumo["ignorados"] == 0
    assert len(chamados) == 2
