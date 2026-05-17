"""
coleta/api_bcb.py
Coleta dados macroeconômicos da API oficial do Banco Central do Brasil.
API pública, gratuita, sem autenticação.

Convenção interna do FIIA:
- selic: taxa anualizada oficial (% a.a.)
- cdi: taxa anualizada oficial (% a.a.)
- ipca: variação mensal oficial

Séries SGS utilizadas:
- SELIC anualizada base 252 → 1178
- CDI anualizado base 252 → 4389
- IPCA oficial → 433
"""
from __future__ import annotations

import requests
from datetime import date
from typing import Optional

from banco import db
from config.settings import URL_BCB_CDI, URL_BCB_IPCA, URL_BCB_SELIC

_CACHE_MEMORIA: dict[str, float | None] = {
    "selic": None,
    "cdi": None,
    "ipca": None,
}


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


def coletar_macro(forcar_atualizacao: bool = False) -> dict:
    """Coleta SELIC, CDI e IPCA do BCB e salva no banco."""
    hoje = date.today().isoformat()

    existente = db.buscar_um("SELECT * FROM macro WHERE data = ?", (hoje,))
    if existente and not forcar_atualizacao:
        print(f"[bcb] Macro já coletado para {hoje}")
        return dict(existente)

    selic = _buscar_valor(URL_BCB_SELIC)
    cdi = _buscar_valor(URL_BCB_CDI)
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
    _CACHE_MEMORIA.update({"selic": selic, "cdi": cdi, "ipca": ipca})

    print(
        f"[bcb] Macro coletado → "
        f"SELIC: {selic}% a.a. | "
        f"CDI: {cdi}% a.a. | "
        f"IPCA: {ipca}%"
    )
    return registro


def corrigir_macro_cdi_diario_gravado() -> dict:
    """
    Corrige registros antigos que foram gravados como taxa diária.

    Estratégia:
    - se valor estiver entre 0 e 1, substitui pela coleta oficial atual;
    - registros já corretos permanecem intactos.
    """
    rows = db.buscar_todos("SELECT id, selic, cdi FROM macro")

    selic_oficial = _buscar_valor(URL_BCB_SELIC)
    cdi_oficial = _buscar_valor(URL_BCB_CDI)

    corrigidos = 0

    for row in rows:
        selic = row["selic"]
        cdi = row["cdi"]

        nova_selic = selic_oficial if selic is not None and 0 < float(selic) < 1 else selic
        novo_cdi = cdi_oficial if cdi is not None and 0 < float(cdi) < 1 else cdi

        if nova_selic != selic or novo_cdi != cdi:
            db.executar(
                "UPDATE macro SET selic = ?, cdi = ? WHERE id = ?",
                (nova_selic, novo_cdi, row["id"]),
            )
            corrigidos += 1

    _CACHE_MEMORIA.update({"selic": None, "cdi": None, "ipca": None})

    return {
        "registros_lidos": len(rows),
        "registros_corrigidos": corrigidos,
        "selic_oficial": selic_oficial,
        "cdi_oficial": cdi_oficial,
    }


def obter_cdi_atual() -> Optional[float]:
    """Retorna o CDI anualizado mais recente disponível."""
    if _CACHE_MEMORIA.get("cdi") is not None:
        return _CACHE_MEMORIA["cdi"]

    hoje = date.today().isoformat()
    row = db.buscar_um(
        "SELECT cdi FROM macro WHERE data <= ? ORDER BY data DESC LIMIT 1",
        (hoje,),
    )

    if row and row["cdi"] is not None:
        _CACHE_MEMORIA["cdi"] = float(row["cdi"])
        return float(row["cdi"])

    dados = coletar_macro()
    return dados.get("cdi")


def obter_selic_atual() -> Optional[float]:
    """Retorna a SELIC anualizada mais recente disponível."""
    if _CACHE_MEMORIA.get("selic") is not None:
        return _CACHE_MEMORIA["selic"]

    hoje = date.today().isoformat()
    row = db.buscar_um(
        "SELECT selic FROM macro WHERE data <= ? ORDER BY data DESC LIMIT 1",
        (hoje,),
    )

    if row and row["selic"] is not None:
        _CACHE_MEMORIA["selic"] = float(row["selic"])
        return float(row["selic"])

    dados = coletar_macro()
    return dados.get("selic")


def obter_ipca_atual() -> Optional[float]:
    """Retorna o IPCA mais recente."""
    if _CACHE_MEMORIA.get("ipca") is not None:
        return _CACHE_MEMORIA["ipca"]

    hoje = date.today().isoformat()
    row = db.buscar_um(
        "SELECT ipca FROM macro WHERE data <= ? ORDER BY data DESC LIMIT 1",
        (hoje,),
    )

    if row and row["ipca"] is not None:
        _CACHE_MEMORIA["ipca"] = row["ipca"]
        return row["ipca"]

    dados = coletar_macro()
    return dados.get("ipca")
