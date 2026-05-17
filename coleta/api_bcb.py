"""
coleta/api_bcb.py
Coleta dados macroeconômicos da API oficial do Banco Central do Brasil.
API pública, gratuita, sem autenticação.

Convenção interna do FIIA:
- selic: taxa anual em percentual (% a.a.)
- cdi: taxa anualizada em percentual (% a.a.)
- ipca: valor retornado pela série configurada no BCB

Observação crítica:
A série SGS 12 do BCB retorna CDI over diário em percentual ao dia.
O FIIA precisa do CDI anualizado para comparar com DY, prêmio CDI e benchmarks.
"""
from __future__ import annotations

import requests
from datetime import date
from typing import Optional

from config.settings import URL_BCB_SELIC, URL_BCB_CDI, URL_BCB_IPCA
from banco import db

_DIAS_UTEIS_ANO = 252


def _buscar_valor(url: str) -> Optional[float]:
    """Busca o valor mais recente de uma série do BCB."""
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        dados = resp.json()
        if dados:
            return float(dados[-1]["valor"].replace(",", "."))
    except Exception as e:
        print(f"[bcb] Erro ao buscar {url}: {e}")
    return None


def _anualizar_taxa_diaria_percentual(taxa_diaria_pct: float | None) -> Optional[float]:
    """Converte taxa diária em percentual para taxa anualizada em percentual."""
    if taxa_diaria_pct is None:
        return None
    return round(((1 + float(taxa_diaria_pct) / 100) ** _DIAS_UTEIS_ANO - 1) * 100, 4)


def coletar_macro(forcar_atualizacao: bool = False) -> dict:
    """
    Coleta SELIC, CDI e IPCA do BCB e salva no banco.

    SELIC vem da série configurada já em % a.a.
    CDI vem da série SGS 12 em % ao dia e é convertido para % a.a.
    """
    hoje = date.today().isoformat()

    existente = db.buscar_um("SELECT * FROM macro WHERE data = ?", (hoje,))
    if existente and not forcar_atualizacao:
        print(f"[bcb] Macro já coletado para {hoje}")
        return dict(existente)

    selic = _buscar_valor(URL_BCB_SELIC)
    cdi_diario = _buscar_valor(URL_BCB_CDI)
    cdi = _anualizar_taxa_diaria_percentual(cdi_diario)
    ipca = _buscar_valor(URL_BCB_IPCA)

    if selic is None and cdi is None:
        print("[bcb] Falha na coleta — sem dados disponíveis")
        return {}

    registro = {
        "data": hoje,
        "selic": selic,
        "cdi": cdi,
        "ipca": ipca,
        "ifix": None,
    }

    db.upsert("macro", registro)
    print(
        f"[bcb] Macro coletado → SELIC: {selic}% a.a. | "
        f"CDI: {cdi}% a.a. (diário BCB: {cdi_diario}%) | IPCA: {ipca}%"
    )
    return registro


def corrigir_macro_cdi_diario_gravado() -> dict:
    """
    Corrige registros antigos gravados com CDI diário e/ou SELIC diária.

    Heurística segura:
    - se cdi está entre 0 e 1, assume que foi gravado como CDI diário e anualiza;
    - se selic está entre 0 e 1, substitui pela SELIC anual mais recente do BCB.

    Essa correção deve ser executada uma vez após o bugfix.
    """
    selic_atual = _buscar_valor(URL_BCB_SELIC)
    rows = db.buscar_todos("SELECT id, data, selic, cdi FROM macro ORDER BY data")

    corrigidos_cdi = 0
    corrigidos_selic = 0

    for row in rows:
        selic = row["selic"]
        cdi = row["cdi"]
        nova_selic = selic
        novo_cdi = cdi

        if cdi is not None and 0 < float(cdi) < 1:
            novo_cdi = _anualizar_taxa_diaria_percentual(float(cdi))
            corrigidos_cdi += 1

        if selic is not None and 0 < float(selic) < 1 and selic_atual is not None:
            nova_selic = selic_atual
            corrigidos_selic += 1

        if nova_selic != selic or novo_cdi != cdi:
            db.executar(
                "UPDATE macro SET selic = ?, cdi = ? WHERE id = ?",
                (nova_selic, novo_cdi, row["id"]),
            )

    return {
        "registros_lidos": len(rows),
        "cdi_diario_anualizado": corrigidos_cdi,
        "selic_diaria_substituida": corrigidos_selic,
        "selic_referencia": selic_atual,
    }


def obter_cdi_atual() -> Optional[float]:
    """Retorna o CDI anualizado mais recente disponível no banco."""
    hoje = date.today().isoformat()
    row = db.buscar_um(
        "SELECT cdi FROM macro WHERE data <= ? ORDER BY data DESC LIMIT 1",
        (hoje,),
    )
    if row and row["cdi"]:
        cdi = float(row["cdi"])
        if 0 < cdi < 1:
            return _anualizar_taxa_diaria_percentual(cdi)
        return cdi

    dados = coletar_macro()
    return dados.get("cdi")


def obter_selic_atual() -> Optional[float]:
    """Retorna a SELIC anual mais recente disponível."""
    hoje = date.today().isoformat()
    row = db.buscar_um(
        "SELECT selic FROM macro WHERE data <= ? ORDER BY data DESC LIMIT 1",
        (hoje,),
    )
    if row and row["selic"]:
        selic = float(row["selic"])
        if 0 < selic < 1:
            selic_bcb = _buscar_valor(URL_BCB_SELIC)
            return selic_bcb if selic_bcb is not None else selic
        return selic

    dados = coletar_macro()
    return dados.get("selic")


def obter_ipca_atual() -> Optional[float]:
    """Retorna o IPCA mais recente."""
    hoje = date.today().isoformat()
    row = db.buscar_um(
        "SELECT ipca FROM macro WHERE data <= ? ORDER BY data DESC LIMIT 1",
        (hoje,),
    )
    if row and row["ipca"]:
        return row["ipca"]
    dados = coletar_macro()
    return dados.get("ipca")
