"""
processamento/estrategia.py
Radar principal do FIIA.
"""

import time
from typing import Tuple, List
from banco import db


def aplicar_filtros_sobrevivencia(ticker: str) -> Tuple[bool, List[str]]:
    from decisao.decisao_com_confianca import decidir

    veredito = decidir(ticker)
    gate = veredito.get("gate_parada", 7)
    decisao = veredito.get("decisao", "")

    eliminado = gate < 4 or decisao.startswith("BLOQUEADO") or decisao.startswith("ELIMINADO")

    if eliminado:
        return False, [veredito.get("motivo", "Eliminado pelo pipeline de qualidade.")]

    return True, []


def radar_oportunidades() -> list:
    from coleta.api_fundamentus import coletar_mercado_inteiro
    from processamento.analise_qualitativa import analisar_fundo_ia
    from decisao.decisao_com_confianca import decidir
    from decisao.persistencia_decisao import gravar
    from coleta.contexto_ativo import obter_contexto_ativo

    mercado = coletar_mercado_inteiro()

    print("\n" + "="*60)
    print("  FIIA RADAR - CVM-first + Confiança Consolidada")
    print("="*60)

    sobreviventes_a = []

    for fii in mercado:
        ticker = fii["ticker"]
        segmento = fii.get("segmento", "")
        liquidez = fii.get("liquidez") or 0.0

        if liquidez < 1_000_000:
            continue

        eh_papel = "PAPEL" in segmento.upper() or "RECEB" in segmento.upper()
        if not eh_papel:
            vacancia = fii.get("vacancia_media")
            if vacancia is not None and vacancia > 20.0:
                continue

        sobreviventes_a.append(ticker)

    candidatos_preco = []
    log_gates = {}
    finalistas = []

    for ticker in sobreviventes_a[:50]:
        # 1. Carrega e Audita o Contexto do Ativo
        contexto = obter_contexto_ativo(ticker)

        # 2. Se o contexto bloquear a decisão (fail-closed), gera o card de bloqueio imediatamente
        if not contexto.get("permitir_decisao", True):
            veredito_bloqueado = {
                "ticker": ticker,
                "decisao": f"BLOQUEADO_DADOS_{contexto.get('nivel_uso_dados', 'INSUFICIENTE')}",
                "motivo": f"Campos ausentes: {', '.join(contexto.get('campos_ausentes', []))}. Campos vencidos: {', '.join(contexto.get('campos_vencidos', []))}.",
                "permitir_decisao": False,
                "campos_ausentes": contexto.get("campos_ausentes", []),
                "campos_vencidos": contexto.get("campos_vencidos", []),
                "fontes_falharam": contexto.get("fontes_falharam", []),
                "score_confianca_dados_consolidado": contexto.get("score_confianca", 0.0),
                "nivel_uso_dados_consolidado": contexto.get("nivel_uso_dados", "INSUFICIENTE"),
                "preco": contexto.get("preco") or 0.0,
                "preco_atual": contexto.get("preco") or 0.0,
                "preco_justo": None,
                "preco_entrada": None,
                "margem": 0.0,
                "pvp": contexto.get("pvp") or 0.0,
                "vpa": contexto.get("vpa") or 0.0,
                "dy_12m": contexto.get("dy_12m") or 0.0,
                "dy_12m_pct": (contexto.get("dy_12m") or 0.0) * 100,
                "gate_parada": 0,
                "trilha_gates": ["Gate 0: BLOQUEADO_DADOS_INSUFICIENTES"],
                "confianca": "BAIXA",
                "alertas": [f"Fontes falharam: {', '.join(contexto.get('fontes_falharam', []))}"] if contexto.get("fontes_falharam") else [],
                "score_ia": 0.0,
            }
            gravar(veredito_bloqueado)
            finalistas.append({"ticker": ticker, "margem": 0.0, "veredito": veredito_bloqueado})
            continue

        # Roda o motor atual com o contexto já normalizado e persistido
        veredito = decidir(ticker, ia_status="INDISPONIVEL", contexto=contexto)
        gate_parada = veredito.get("gate_parada", 0)

        log_gates[gate_parada] = log_gates.get(gate_parada, 0) + 1

        if gate_parada < 4 or gate_parada == 55:
            continue

        candidatos_preco.append({"ticker": ticker, "contexto": contexto})

    com_margem = []

    for item in candidatos_preco:
        veredito = decidir(item["ticker"], ia_status="INDISPONIVEL", contexto=item["contexto"])
        margem = veredito.get("margem")

        if margem is not None and margem > 0:
            com_margem.append({"ticker": item["ticker"], "margem": margem, "contexto": item["contexto"]})

    com_margem.sort(key=lambda x: x["margem"], reverse=True)
    top = com_margem[:30]

    for i, item in enumerate(top):
        ticker = item["ticker"]

        qual = analisar_fundo_ia(ticker)
        time.sleep(3)

        veredito = decidir(
            ticker=ticker,
            score_ia=qual.get("score"),
            riscos_ia=qual.get("riscos"),
            tom_gestor=qual.get("tom_gestor"),
            ia_status=qual.get("status", "INDISPONIVEL"),
            contexto=item["contexto"],
        )

        item["veredito"] = veredito
        gravar(veredito)
        finalistas.append(item)

    print("\nDecisões finais:\n")

    for item in finalistas:
        v = item["veredito"]
        score_conf = (
            v.get("score_confianca_dados_consolidado")
            or v.get("score_confianca_dados")
            or 0
        )

        print(
            f"  {v.get('ticker','?'):8s} | "
            f"{v.get('decisao','?'):15s} | "
            f"margem {v.get('margem')}% | "
            f"gate_parada={v.get('gate_parada')} | "
            f"confiança={score_conf} | "
            f"patrimonial={v.get('fonte_patrimonial', 'N/D')}"
        )

    return finalistas
