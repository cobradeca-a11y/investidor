"""
processamento/estrategia.py
Filtros de sobrevivência e radar de oportunidades.

Correções aplicadas:
  - vacancia_media None não causa mais TypeError no radar
  - liquidez None tratada com fallback 0.0
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

    # 2. Vacância máxima 15% — apenas fundos de tijolo
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
    Funil de 2 estágios:
      1. Pré-filtro massivo por liquidez, vacância e diversificação.
      2. Deep Scan dos sobreviventes para calcular margem de segurança.
      3. Análise qualitativa com IA no Top 1 (plano gratuito Gemini).
    """
    from coleta.api_fundamentus import coletar_mercado_inteiro, coletar_fii
    from coleta.api_yfinance import coletar_historico_dividendos
    from processamento.margem_seguranca import calcular_margem_seguranca
    from processamento.analise_qualitativa import analisar_fundo_ia

    # ── Estágio 1: varredura de mercado ──────────────────────────────────
    mercado = coletar_mercado_inteiro()
    elite   = []

    print("[radar] Aplicando filtros de sobrevivência iniciais...")
    for fii in mercado:
        ticker   = fii["ticker"]
        segmento = fii.get("segmento", "")

        # Liquidez — None tratado como 0
        liquidez = fii.get("liquidez") or 0.0
        if liquidez < 1_000_000:
            continue

        # Vacância e diversificação — apenas tijolo
        if "PAPEL" not in segmento and "RECEBÍVEIS" not in segmento:
            # FIX: vacancia_media pode ser None para fundos de papel listados como tijolo
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

    # ── Estágio 3: análise qualitativa — Top 1 (plano gratuito) ──────────
    top = oportunidades[:15]
    for fii in top[:1]:
        print(f"\n[radar] Investigando {fii['ticker']} com IA...")
        fii["qualitativo"] = analisar_fundo_ia(fii["ticker"])
        time.sleep(4)

    return top
