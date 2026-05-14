"""
processamento/estrategia.py
Filtros de sobrevivência e radar de oportunidades - v2.1.

Mudanças v2.1:
  - Pipeline eliminatório real: cada fundo mostra em qual gate parou.
  - Deep scan só em fundos que sobreviveram até Gate 3 inclusive.
  - IA só roda nos finalistas do Gate 4 (margem positiva).
  - Console mostra trilha de gates por fundo - nunca caixa preta.
"""

import time
from typing import Tuple, List
from banco import db


def aplicar_filtros_sobrevivencia(ticker: str) -> Tuple[bool, List[str]]:
    """
    Atalho de verificação rápida para uso externo (ex: UI, validações pontuais).
    Retorna (aprovado, [motivos_reprovacao]).
    Para análise completa, use radar_oportunidades() ou motor_decisao.decidir().
    """
    from decisao.motor_decisao import decidir

    veredito = decidir(ticker)
    gate     = veredito.get("gate_parada", 7)
    decisao  = veredito.get("decisao", "")

    eliminado = gate < 4 or decisao.startswith("BLOQUEADO") or decisao.startswith("ELIMINADO")

    if eliminado:
        return False, [veredito.get("motivo", "Eliminado pelo pipeline de qualidade.")]

    return True, []


def radar_oportunidades() -> list:
    """
    Esteira de qualidade - 4 estágios visíveis no console:

      Estágio A: varredura de mercado com pré-filtros de liquidez e vacância
      Estágio B: deep scan + gates 0–3 (qualidade obrigatória)
      Estágio C: gate 4 (preço) - só os que passaram em estrutura e renda
      Estágio D: IA + veredito final - só os com margem positiva

    A trilha de cada fundo é exibida no console.
    O retorno são apenas os fundos que chegaram ao Estágio D.
    """
    from coleta.api_fundamentus import coletar_mercado_inteiro, coletar_fii
    from coleta.api_yfinance import coletar_historico_dividendos
    from processamento.analise_qualitativa import analisar_fundo_ia
    from decisao.motor_decisao import decidir
    from decisao.persistencia_decisao import gravar

    # ── Estágio A: varredura de mercado ──────────────────────────────────
    mercado = coletar_mercado_inteiro()

    print("\n" + "="*60)
    print("  FIIA RADAR v2.1 - Esteira de Qualidade 8 Gates")
    print("="*60)
    print(f"\n[A] Mercado: {len(mercado)} FIIs encontrados.")
    print("[A] Aplicando pré-filtros iniciais (liquidez + vacância)...\n")

    sobreviventes_a = []
    eliminados_a    = {"liquidez": 0, "vacancia": 0}

    for fii in mercado:
        ticker   = fii["ticker"]
        segmento = fii.get("segmento", "")
        liquidez = fii.get("liquidez") or 0.0

        if liquidez < 1_000_000:
            eliminados_a["liquidez"] += 1
            continue

        eh_papel = "PAPEL" in segmento.upper() or "RECEB" in segmento.upper()
        if not eh_papel:
            vacancia = fii.get("vacancia_media")
            if vacancia is not None and vacancia > 20.0:
                eliminados_a["vacancia"] += 1
                continue

        sobreviventes_a.append(ticker)

    print(f"[A] Eliminados por liquidez  : {eliminados_a['liquidez']}")
    print(f"[A] Eliminados por vacância  : {eliminados_a['vacancia']}")
    print(f"[A] Passaram para deep scan  : {len(sobreviventes_a)}\n")

    # ── Estágio B: deep scan + gates 0–3 ─────────────────────────────────
    # Coleta dados completos e roda os gates de qualidade obrigatórios.
    # Fundo que cair em qualquer gate 0–3 é descartado antes do preço.

    print("[B] Deep scan + Gates 0–3 (validação, elegibilidade, estrutura, renda)...")
    print("    Limite: primeiros 50 fundos do Estágio A.\n")

    candidatos_preco = []   # fundos que passaram nos gates 0–3
    log_gates = {0: 0, 1: 0, 2: 0, 3: 0}

    for ticker in sobreviventes_a[:50]:
        print(f"    [{ticker}] coletando...", end="\r")
        coletar_fii(ticker)
        coletar_historico_dividendos(ticker)

        # Roda apenas os gates 0–3 via decidir() com IA desligada
        # O decidir() com ia_status=INDISPONIVEL para no gate mais alto possível
        # sem IA - mas os gates 0–3 não dependem de IA.
        veredito = decidir(ticker, ia_status="INDISPONIVEL")
        gate_parada = veredito.get("gate_parada", 0)
        decisao     = veredito.get("decisao", "")
        trilha      = " -> ".join(veredito.get("trilha_gates", []))

        # Fundo bloqueado ou eliminado antes do gate 4
        if gate_parada < 4:
            log_gates[gate_parada] = log_gates.get(gate_parada, 0) + 1
            status_gate = veredito["gates_detalhes"].get(str(gate_parada), {}).get("status", "?")
            print(f"    [{ticker}] X Gate {gate_parada} ({status_gate}): {veredito['motivo'][:80]}")
            continue

        # Passou pelos gates de qualidade - agora avaliamos o preço
        margem = veredito.get("margem")
        print(f"    [{ticker}] OK Gates 0–3 OK | margem={margem}%")
        candidatos_preco.append({"ticker": ticker, "veredito_parcial": veredito})

    print(f"\n[B] Eliminados no Gate 0 (dados)    : {log_gates.get(0, 0)}")
    print(f"[B] Eliminados no Gate 1 (elegib.)  : {log_gates.get(1, 0)}")
    print(f"[B] Eliminados no Gate 2 (estrutura): {log_gates.get(2, 0)}")
    print(f"[B] Eliminados no Gate 3 (renda)    : {log_gates.get(3, 0)}")
    print(f"[B] Sobreviventes para Gate 4       : {len(candidatos_preco)}\n")

    # ── Estágio C: gate 4 (preço) ─────────────────────────────────────────
    # Só chegam aqui fundos com estrutura e renda aprovadas.
    # Ordena por margem de segurança.

    print("[C] Gate 4 - Classificação por preço e margem de segurança...")

    com_margem = []
    sem_margem = []

    for item in candidatos_preco:
        veredito = item["veredito_parcial"]
        margem   = veredito.get("margem")

        if margem is None:
            sem_margem.append(item["ticker"])
            print(f"    [{item['ticker']}] X Margem incalculável")
        elif margem <= 0:
            sem_margem.append(item["ticker"])
            print(f"    [{item['ticker']}] X Margem negativa ({margem}%) - evitar")
        else:
            com_margem.append({"ticker": item["ticker"], "margem": margem})
            print(f"    [{item['ticker']}] OK Margem {margem}%")

    com_margem.sort(key=lambda x: x["margem"], reverse=True)
    top = com_margem[:30]

    print(f"\n[C] Com margem positiva : {len(com_margem)}")
    print(f"[C] Sem margem / evitar : {len(sem_margem)}")
    print(f"[C] Top selecionados    : {len(top)}\n")

    # ── Estágio D: IA + veredito final ───────────────────────────────────
    # A IA só roda nos finalistas com margem positiva.
    # A IA não aprova - apenas veta ou complementa.

    print(f"[D] Gate 6 - Análise qualitativa / IA no Top {len(top)}...")
    finalistas = []

    for i, item in enumerate(top):
        ticker = item["ticker"]
        print(f"    [{ticker}] IA analisando ({i+1}/{len(top)})...")

        qual = analisar_fundo_ia(ticker)
        time.sleep(3)

        veredito = decidir(
            ticker     = ticker,
            score_ia   = qual.get("score"),
            riscos_ia  = qual.get("riscos"),
            tom_gestor = qual.get("tom_gestor"),
            ia_status  = qual.get("status", "INDISPONIVEL"),
        )

        trilha  = " -> ".join(veredito.get("trilha_gates", []))
        decisao = veredito.get("decisao", "?")
        print(f"    [{ticker}] {decisao} | {trilha}")

        item["veredito"] = veredito
        gravar(veredito)
        finalistas.append(item)

    print("\n" + "="*60)
    print(f"  RADAR CONCLUÍDO - {len(finalistas)} finalistas")
    print("="*60)
    print("\nDecisões finais:")
    for item in finalistas:
        v = item["veredito"]
        print(f"  {v['ticker']:8s} | {v['decisao']:15s} | margem {v.get('margem')}% | "
              f"gate_parada={v['gate_parada']} | confiança={v['confianca']}")
    print()

    return finalistas
