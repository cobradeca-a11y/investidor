"""
processamento/estrategia.py
Radar principal do FIIA.
"""

import time
from typing import Tuple, List
from banco import db
from config import settings


def _gate0_bloqueio_contexto(contexto: dict) -> dict:
    campos_ausentes = contexto.get("campos_ausentes", [])
    campos_vencidos = contexto.get("campos_vencidos", [])
    return {
        "gate": 0,
        "status": "BLOQUEADO_DADOS_INSUFICIENTES",
        "aprovado": False,
        "eliminado": True,
        "motivo": "Dados insuficientes para decisao forte.",
        "motivos": [
            f"Campos ausentes: {', '.join(campos_ausentes)}.",
            f"Campos vencidos: {', '.join(campos_vencidos)}.",
        ],
        "metricas": {
            "campos_ausentes": campos_ausentes,
            "campos_vencidos": campos_vencidos,
            "score_confianca": contexto.get("score_confianca"),
            "liquidez_diaria": contexto.get("liquidez_diaria"),
        },
        "fontes": ["contexto_ativo"],
        "penalidades": campos_ausentes + campos_vencidos,
    }


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
    gate0 = _gate0_bloqueio_contexto(contexto)
    score_confianca = contexto.get("score_confianca", 0.0)
    nivel_uso = contexto.get("nivel_uso_dados", "INSUFICIENTE")
    return {
        "ticker": ticker,
        "decisao": f"BLOQUEADO_DADOS_{nivel_uso}",
        "motivo": f"Campos ausentes: {', '.join(contexto.get('campos_ausentes', []))}. Campos vencidos: {', '.join(contexto.get('campos_vencidos', []))}.",
        "permitir_decisao": False,
        "contexto_versao": contexto.get("contexto_versao"),
        "versao_modelo": "2.1",
        "versao_motor": "2.1",
        "segmento": contexto.get("segmento"),
        "fonte_patrimonial": contexto.get("patrimonio_fonte"),
        "patrimonio_fonte": contexto.get("patrimonio_fonte"),
        "campos_ausentes": contexto.get("campos_ausentes", []),
        "campos_vencidos": contexto.get("campos_vencidos", []),
        "fontes_falharam": contexto.get("fontes_falharam", []),
        "score_confianca_dados": score_confianca,
        "score_confianca_dados_consolidado": score_confianca,
        "nivel_uso_dados": nivel_uso,
        "nivel_uso_dados_consolidado": nivel_uso,
        "confianca_dados": {"score_global": score_confianca, "nivel_uso": nivel_uso},
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
        "gates_detalhes": {"0": gate0},
        "confianca": "BAIXA",
        "alertas": [f"Fontes falharam: {', '.join(contexto.get('fontes_falharam', []))}"] if contexto.get("fontes_falharam") else [],
        "score_ia": 0.0,
    }


def _atualizar_permissao_contexto(contexto: dict) -> dict:
    campos_ausentes = list(dict.fromkeys(contexto.get("campos_ausentes", [])))
    if contexto.get("liquidez_diaria") and contexto.get("liquidez_diaria") >= settings.LIQUIDEZ_MINIMA_DIARIA:
        campos_ausentes = [campo for campo in campos_ausentes if campo != "liquidez"]

    contexto["campos_ausentes"] = campos_ausentes
    contexto["permitir_decisao"] = (
        not campos_ausentes
        and contexto.get("preco") is not None
        and contexto.get("vpa") is not None
        and (contexto.get("score_confianca") or 0) >= settings.CONFIABILIDADE_MINIMA
    )
    return contexto


def _aplicar_hint_mercado_contexto(contexto: dict, hint: dict | None) -> dict:
    """Complementa contexto com dados ja coletados no mercado inteiro do Fundamentus."""
    if not hint:
        return contexto

    contexto = dict(contexto)
    liquidez_hint = hint.get("liquidez")
    if liquidez_hint and not contexto.get("liquidez_diaria"):
        contexto["liquidez_diaria"] = liquidez_hint
        contexto["liquidez_fonte"] = "FundamentusMercado"

    for campo_ctx, campo_hint in {
        "segmento": "segmento",
        "preco": "preco",
        "pvp": "pvp",
        "dy_12m": "dy_12m",
        "qtd_ativos": "qtd_ativos",
        "vacancia_fisica": "vacancia_media",
    }.items():
        valor = hint.get(campo_hint)
        if valor is not None and contexto.get(campo_ctx) in (None, "", 0, 0.0, "INDEFINIDO"):
            contexto[campo_ctx] = valor

    return _atualizar_permissao_contexto(contexto)


def _somar_falhas_por_fonte(destino: dict[str, int], fontes: list[str] | None) -> None:
    for fonte in fontes or []:
        destino[fonte] = destino.get(fonte, 0) + 1


def _resolver_contextos_ciclo(tickers: list[str], metricas: dict | None = None, hints_mercado: dict[str, dict] | None = None) -> dict[str, dict]:
    """
    Resolve contextos para um ciclo de radar com cache local e versionado.

    O cache do ciclo evita chamadas duplicadas para o mesmo ticker e só reutiliza
    contexto com a VERSAO_CONTEXTO vigente. Contextos vencidos/de versão antiga
    são obtidos novamente via resolver oficial.
    """
    from coleta.contexto_ativo import obter_contexto_ativo, VERSAO_CONTEXTO

    cache_ciclo: dict[str, dict] = {}
    resultado: dict[str, dict] = {}
    metricas = metricas if metricas is not None else {}
    metricas.setdefault("cache_hits", 0)
    metricas.setdefault("cache_misses", 0)
    metricas.setdefault("contextos_regenerados", 0)

    for ticker in tickers:
        ticker_norm = ticker.upper().replace(".SA", "").strip()
        if not ticker_norm:
            continue

        contexto_cache = cache_ciclo.get(ticker_norm)
        if contexto_cache and contexto_cache.get("contexto_versao") == VERSAO_CONTEXTO:
            metricas["cache_hits"] += 1
            resultado[ticker_norm] = contexto_cache
            continue

        metricas["cache_misses"] += 1
        contexto = obter_contexto_ativo(ticker_norm)
        if contexto.get("contexto_versao") != VERSAO_CONTEXTO:
            metricas["contextos_regenerados"] += 1
            contexto = obter_contexto_ativo(ticker_norm)

        contexto = _aplicar_hint_mercado_contexto(contexto, (hints_mercado or {}).get(ticker_norm))
        cache_ciclo[ticker_norm] = contexto
        resultado[ticker_norm] = contexto

    return resultado


def radar_oportunidades() -> list:
    from coleta.api_fundamentus import coletar_mercado_inteiro
    from processamento.analise_qualitativa import analisar_fundo_ia
    from decisao.decisao_com_confianca import decidir
    from decisao.persistencia_decisao import gravar
    from sistema.observabilidade import registrar_metrica_performance

    inicio_radar = time.perf_counter()
    metricas_radar = {
        "ativos_mercado": 0,
        "ativos_sobreviventes": 0,
        "ativos_bloqueados": 0,
        "ativos_gate_eliminados": 0,
        "ativos_com_margem": 0,
        "ativos_finalistas": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "contextos_regenerados": 0,
        "tempo_coleta_ms": 0,
        "tempo_decisao_ms": 0,
        "tempo_ia_ms": 0,
        "falhas_por_fonte": {},
    }

    inicio_coleta = time.perf_counter()
    mercado = coletar_mercado_inteiro()
    metricas_radar["tempo_coleta_ms"] += round((time.perf_counter() - inicio_coleta) * 1000, 2)
    metricas_radar["ativos_mercado"] = len(mercado)

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

    metricas_radar["ativos_sobreviventes"] = len(sobreviventes_a)

    candidatos_preco = []
    log_gates = {}
    finalistas = []

    tickers_radar = sobreviventes_a[:50]
    hints_mercado = {fii["ticker"].upper().replace(".SA", "").strip(): fii for fii in mercado if fii.get("ticker")}
    inicio_contextos = time.perf_counter()
    contextos = _resolver_contextos_ciclo(tickers_radar, metricas=metricas_radar, hints_mercado=hints_mercado)
    metricas_radar["tempo_coleta_ms"] += round((time.perf_counter() - inicio_contextos) * 1000, 2)

    for ticker in tickers_radar:
        ticker_norm = ticker.upper().replace(".SA", "").strip()
        contexto = contextos.get(ticker_norm)
        if not contexto:
            continue

        _somar_falhas_por_fonte(metricas_radar["falhas_por_fonte"], contexto.get("fontes_falharam"))

        if not contexto.get("permitir_decisao", True):
            metricas_radar["ativos_bloqueados"] += 1
            veredito_bloqueado = _card_bloqueio_contexto(ticker_norm, contexto)
            gravar(veredito_bloqueado)
            finalistas.append({"ticker": ticker_norm, "margem": 0.0, "veredito": veredito_bloqueado})
            continue

        inicio_decisao = time.perf_counter()
        veredito_pre_ia = decidir(ticker_norm, ia_status="INDISPONIVEL", contexto=contexto)
        metricas_radar["tempo_decisao_ms"] += round((time.perf_counter() - inicio_decisao) * 1000, 2)
        gate_parada = veredito_pre_ia.get("gate_parada", 0)

        log_gates[gate_parada] = log_gates.get(gate_parada, 0) + 1

        if gate_parada < 4 or gate_parada == 55:
            metricas_radar["ativos_gate_eliminados"] += 1
            continue

        margem = veredito_pre_ia.get("margem")
        if margem is not None and margem > 0:
            metricas_radar["ativos_com_margem"] += 1
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

        inicio_ia = time.perf_counter()
        qual = analisar_fundo_ia(ticker)
        metricas_radar["tempo_ia_ms"] += round((time.perf_counter() - inicio_ia) * 1000, 2)
        time.sleep(3)

        inicio_decisao = time.perf_counter()
        veredito = decidir(
            ticker=ticker,
            score_ia=qual.get("score"),
            riscos_ia=qual.get("riscos"),
            tom_gestor=qual.get("tom_gestor"),
            ia_status=qual.get("status", "INDISPONIVEL"),
            contexto=item["contexto"],
        )
        metricas_radar["tempo_decisao_ms"] += round((time.perf_counter() - inicio_decisao) * 1000, 2)

        item["veredito"] = veredito
        gravar(veredito)
        finalistas.append(item)

    metricas_radar["ativos_finalistas"] = len(finalistas)
    metricas_radar["tempo_total_ms"] = round((time.perf_counter() - inicio_radar) * 1000, 2)

    registrar_metrica_performance(
        "processamento.estrategia",
        "radar_oportunidades",
        metricas_radar,
    )

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
