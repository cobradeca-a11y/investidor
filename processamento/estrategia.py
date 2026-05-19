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


def _card_bloqueio_contexto(ticker: str, contexto: dict) -> dict:
    """Monta card de bloqueio mantendo o contrato atual do Radar."""
    return {
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


def _resolver_contextos_ciclo(tickers: list[str]) -> dict[str, dict]:
    """
    Resolve contextos para um ciclo de radar com cache local e versionado.

    O cache do ciclo evita chamadas duplicadas para o mesmo ticker e só reutiliza
    contexto com a VERSAO_CONTEXTO vigente. Contextos vencidos/de versão antiga
    são obtidos novamente via resolver oficial.
    """
    from coleta.contexto_ativo import obter_contexto_ativo, VERSAO_CONTEXTO

    cache_ciclo: dict[str, dict] = {}
    resultado: dict[str, dict] = {}

    for ticker in tickers:
        ticker_norm = ticker.upper().replace(".SA", "").strip()
        if not ticker_norm:
            continue

        contexto_cache = cache_ciclo.get(ticker_norm)
        if contexto_cache and contexto_cache.get("contexto_versao") == VERSAO_CONTEXTO:
            resultado[ticker_norm] = contexto_cache
            continue

        contexto = obter_contexto_ativo(ticker_norm)
        if contexto.get("contexto_versao") != VERSAO_CONTEXTO:
            contexto = obter_contexto_ativo(ticker_norm)

        cache_ciclo[ticker_norm] = contexto
        resultado[ticker_norm] = contexto

    return resultado


def radar_oportunidades() -> list:
    from coleta.api_fundamentus import coletar_mercado_inteiro
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
    finalistas = []

    # Resolve contextos em lote local para evitar recomputação no mesmo ciclo.
    tickers_radar = sobreviventes_a[:50]
    contextos = _resolver_contextos_ciclo(tickers_radar)

    for ticker in tickers_radar:
        ticker_norm = ticker.upper().replace(".SA", "").strip()
        contexto = contextos.get(ticker_norm)
        if not contexto:
            continue

        # Se o contexto bloquear a decisão (fail-closed), gera o card de bloqueio imediatamente.
        if not contexto.get("permitir_decisao", True):
            veredito_bloqueado = _card_bloqueio_contexto(ticker_norm, contexto)
            gravar(veredito_bloqueado)
            finalistas.append({"ticker": ticker_norm, "margem": 0.0, "veredito": veredito_bloqueado})
            continue

        # Roda o motor atual uma única vez sem IA. O mesmo veredito é reaproveitado
        # para gate e margem, evitando recalcular contexto/decisão no mesmo ciclo.
        veredito_pre_ia = decidir(ticker_norm, ia_status="INDISPONIVEL", contexto=contexto)
        gate_parada = veredito_pre_ia.get("gate_parada", 0)

        log_gates[gate_parada] = log_gates.get(gate_parada, 0) + 1

        if gate_parada < 4 or gate_parada == 55:
            continue

        margem = veredito_pre_ia.get("margem")
        if margem is not None and margem > 0:
            candidatos_preco.append({
                "ticker": ticker_norm,
                "margem": margem,
                "contexto": contexto,
                "veredito_pre_ia": veredito_pre_ia,
            })

    candidatos_preco.sort(key=lambda x: x["margem"], reverse=True)
    top = candidatos_preco[:30]

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