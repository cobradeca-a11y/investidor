"""
processamento/estrategia.py
Filtros de sobrevivência e radar de oportunidades.

Mudanças v2:
  - IA acionada no Top 3 (era Top 1)
  - Motor de decisão integrado em todos os finalistas
  - Decisão gravada no banco automaticamente
  - Radar funciona mesmo sem IA disponível
"""
import time
from typing import Tuple, List
from banco import db


def aplicar_filtros_sobrevivencia(ticker: str) -> Tuple[bool, List[str]]:
    """
    Camada 1: Filtros de Sobrevivência.
    Retorna (aprovado, [motivos_reprovacao]).
    """
    ind_row     = db.buscar_um(
        "SELECT * FROM indicadores WHERE ticker = ? ORDER BY data DESC LIMIT 1",
        (ticker,)
    )
    fii_info_row = db.buscar_um("SELECT * FROM fiis WHERE ticker = ?", (ticker,))

    if not ind_row or not fii_info_row:
        return False, ["Dados insuficientes no banco para avaliação."]

    ind      = dict(ind_row)
    fii_info = dict(fii_info_row)
    motivos  = []

    # 1. Liquidez mínima R$ 1 milhão
    liquidez = ind.get("liquidez_diaria") or 0.0
    if liquidez < 1_000_000:
        val = f"R${liquidez:,.2f}" if liquidez else "Desconhecida"
        motivos.append(f"Liquidez baixa ({val}). Risco de não conseguir vender as cotas.")

    # 2. Vacância máxima 15% - apenas fundos de tijolo
    segmento = fii_info.get("segmento", "").upper()
    if "PAPEL" not in segmento and "RECEBÍVEIS" not in segmento:
        vacancia = ind.get("vacancia_fisica")
        if vacancia is not None and vacancia > 15.0:
            motivos.append(f"Vacância alta ({vacancia}%). Muitos imóveis vazios.")

        # 3. Diversificação mínima de 5 imóveis
        qtd_ativos = ind.get("qtd_ativos")
        if qtd_ativos is not None and qtd_ativos < 5:
            motivos.append(f"Baixa diversificação ({int(qtd_ativos)} imóveis). Risco concentrado.")

    aprovado = len(motivos) == 0
    return aprovado, motivos


def radar_oportunidades() -> list:
    """
    Funil de 4 estágios:
      1. Pré-filtro massivo por liquidez, vacância e diversificação.
      2. Deep Scan dos sobreviventes para calcular margem de segurança.
      3. Análise qualitativa com IA no Top 3.
      4. Motor de decisão em todos os finalistas - decisão gravada no banco.
    """
    from coleta.api_fundamentus import coletar_mercado_inteiro, coletar_fii
    from coleta.api_yfinance import coletar_historico_dividendos
    from processamento.margem_seguranca import calcular_margem_seguranca
    from processamento.analise_qualitativa import analisar_fundo_ia
    from decisao.motor_decisao import decidir
    from decisao.persistencia_decisao import gravar

    # ── Estágio 1: varredura de mercado ──────────────────────────────────
    mercado = coletar_mercado_inteiro()
    elite   = []

    print("[radar] Aplicando filtros de sobrevivência iniciais...")
    for fii in mercado:
        ticker   = fii["ticker"]
        segmento = fii.get("segmento", "")

        liquidez = fii.get("liquidez") or 0.0
        if liquidez < 1_000_000:
            continue

        if "PAPEL" not in segmento and "RECEBÍVEIS" not in segmento:
            vacancia = fii.get("vacancia_media")
            if vacancia is not None and vacancia > 15.0:
                continue

            qtd = fii.get("qtd_ativos")
            if qtd is not None and qtd < 5:
                continue

        elite.append(ticker)

    print(f"[radar] {len(elite)} FIIs passaram para o Raio-X profundo.")

    # ── Estágio 2: deep scan (limitado a 50) ─────────────────────────────
    oportunidades = []

    for ticker in elite[:50]:
        print(f"[radar] Analisando {ticker}...", end="\r")
        coletar_fii(ticker)
        coletar_historico_dividendos(ticker)

        margem = calcular_margem_seguranca(ticker)
        if margem is not None and margem > 0:
            oportunidades.append({"ticker": ticker, "margem": margem})

    oportunidades.sort(key=lambda x: x["margem"], reverse=True)

    # ── Estágio 3: análise qualitativa - Top 30 ──────────────────────────
    top = oportunidades[:30]
    print("\n[radar] Iniciando analise qualitativa no Top 30...")
    for i, fii in enumerate(top):
        ticker = fii["ticker"]
        print(f"[radar] IA analisando {ticker} ({i+1}/{len(top)})...")
        fii["qualitativo"] = analisar_fundo_ia(ticker)
        time.sleep(3)

    # ── Estágio 4: motor de decisão em todos os finalistas ───────────────
    print(f"\n[radar] Gerando vereditos para o Top {len(top)}...")
    for fii in top:
        ticker = fii["ticker"]
        qual   = fii.get("qualitativo") or {}

        veredito = decidir(
            ticker     = ticker,
            score_ia   = qual.get("score"),
            riscos_ia  = qual.get("riscos"),
            tom_gestor = qual.get("tom_gestor"),
            ia_status  = qual.get("status", "INDISPONIVEL"),
        )
        fii["veredito"] = veredito
        gravar(veredito)

    return top
