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
    from coleta.api_fundamentus import coletar_mercado_inteiro, coletar_fii
    from coleta.api_yfinance import coletar_historico_dividendos
    from processamento.analise_qualitativa import analisar_fundo_ia
    from decisao.decisao_com_confianca import decidir
    from decisao.persistencia_decisao import gravar

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

    for ticker in sobreviventes_a[:50]:
        coletar_fii(ticker)
        coletar_historico_dividendos(ticker)

        veredito = decidir(ticker, ia_status="INDISPONIVEL")
        gate_parada = veredito.get("gate_parada", 0)

        log_gates[gate_parada] = log_gates.get(gate_parada, 0) + 1

        if gate_parada < 4 or gate_parada == 55:
            continue

        candidatos_preco.append({"ticker": ticker})

    com_margem = []

    for item in candidatos_preco:
        veredito = decidir(item["ticker"], ia_status="INDISPONIVEL")
        margem = veredito.get("margem")

        if margem is not None and margem > 0:
            com_margem.append({"ticker": item["ticker"], "margem": margem})

    com_margem.sort(key=lambda x: x["margem"], reverse=True)
    top = com_margem[:30]

    finalistas = []

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
