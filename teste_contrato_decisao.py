from coleta.contexto_ativo import obter_contexto_ativo
from decisao import decisao_com_confianca
from decisao.objeto_decisao import (
    CONTRATO_DECISAO_CAMPOS,
    AcaoOperacional,
    DecisaoFIIA,
    NivelConfianca,
    NivelRisco,
    normalizar_contrato_decisao,
)
from decisao.persistencia_decisao import _normalizar_objeto_decisao, _normalizar_veredito
from teste_proibicao_sqlite import IsolamentoZeroDB


def _assert_contrato_decisao(payload: dict) -> None:
    for campo in CONTRATO_DECISAO_CAMPOS:
        assert campo in payload, f"Campo obrigatorio ausente: {campo}"

    assert payload["ticker"]
    assert payload["decisao"]
    assert payload["acao"]
    assert isinstance(payload["trilha_gates"], list)
    assert isinstance(payload["gates_detalhes"], dict)
    assert isinstance(payload["penalidades"], list)
    assert isinstance(payload["alertas"], list)
    assert isinstance(payload["confianca_dados"], dict)

    for gate in payload["gates_detalhes"].values():
        assert "gate" in gate
        assert "status" in gate
        assert "aprovado" in gate
        assert "eliminado" in gate
        assert "motivos" in gate
        assert "metricas" in gate
        assert "fontes" in gate
        assert "penalidades" in gate


def test_contrato_final_decisao_com_contexto_zero_db():
    ticker = "HGLG11"
    contexto = obter_contexto_ativo(ticker)

    with IsolamentoZeroDB():
        veredito = decisao_com_confianca.decidir(
            ticker,
            score_ia=8.5,
            riscos_ia=[],
            tom_gestor="neutro",
            ia_status="OK",
            contexto=contexto,
        )

    _assert_contrato_decisao(veredito)
    assert veredito["ticker"] == ticker
    assert veredito["contexto_versao"] == contexto.get("contexto_versao")


def test_normalizador_preserva_payload_legado():
    legado = {
        "ticker": "XPTO11",
        "decisao": "ELIMINADO_LIQUIDEZ",
        "motivo": "Liquidez insuficiente.",
        "preco_atual": 10.0,
        "trilha_gates": ["Gate 1: ELIMINADO_LIQUIDEZ"],
        "gates_detalhes": {
            "1": {
                "gate": 1,
                "status": "ELIMINADO_LIQUIDEZ",
                "aprovado": False,
                "eliminado": True,
                "motivo": "Liquidez insuficiente.",
                "motivos": ["Liquidez insuficiente."],
                "metricas": {"liquidez": 1000},
                "fontes": [],
                "penalidades": [],
            }
        },
    }

    payload = normalizar_contrato_decisao(legado, {"contexto_versao": "asset-context-test"})

    _assert_contrato_decisao(payload)
    assert payload["decisao"] == "ELIMINADO_LIQUIDEZ"
    assert payload["acao"] == "EVITAR_ENTRADA"

    dados_persistencia = _normalizar_veredito(payload)
    assert dados_persistencia["ticker"] == "XPTO11"
    assert dados_persistencia["decisao"] == "ELIMINADO_LIQUIDEZ"
    assert "payload_json" in dados_persistencia


def test_decisao_fiia_to_dict_contrato_e_persistencia():
    decisao = DecisaoFIIA(
        ticker="HGLG11",
        acao=AcaoOperacional.MONITORAR,
        risco=NivelRisco.MODERADO,
        confianca=NivelConfianca.MEDIA,
        preco_atual=100.0,
        preco_justo=110.0,
        preco_entrada=104.5,
        preco_teto=104.5,
        margem_seguranca=10.0,
        segmento="LOGISTICA",
        contexto={"contexto_versao": "asset-context-test"},
    )
    decisao.decisao = "MONITORAR"
    decisao.motivo = "Contrato formal de decisao."
    decisao.trilha_gates = ["Gate 0: APROVADO_DADOS"]
    decisao.gates_detalhes = {
        "0": {
            "gate": 0,
            "status": "APROVADO_DADOS",
            "aprovado": True,
            "eliminado": False,
            "motivo": "Dados minimos presentes.",
            "motivos": ["Dados minimos presentes."],
            "metricas": {},
            "fontes": [],
            "penalidades": [],
        }
    }

    payload = decisao.to_dict()
    _assert_contrato_decisao(payload)

    dados_persistencia = _normalizar_objeto_decisao(decisao)
    assert dados_persistencia["ticker"] == "HGLG11"
    assert dados_persistencia["decisao"] == "MONITORAR"
    assert dados_persistencia["preco_entrada"] == 104.5
