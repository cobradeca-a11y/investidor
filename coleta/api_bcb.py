"""
coleta/api_bcb.py
Coleta dados macroeconômicos da API oficial do Banco Central do Brasil.
API pública, gratuita, sem autenticação.

Convenção interna do FIIA:
- selic: taxa anualizada em percentual (% a.a.)
- cdi: taxa anualizada em percentual (% a.a.)
- ipca: valor retornado pela série configurada no BCB

Observação crítica:
Algumas séries configuradas podem retornar taxa diária em percentual.
Sempre que SELIC/CDI vierem entre 0 e 1, o FIIA anualiza para % a.a.
"""
from __future__ import annotations

import requests
from datetime import date
from typing import Optional

from config.settings import URL_BCB_SELIC, URL_BCB_CDI, URL_BCB_IPCA
from banco import db

_DIAS_UTEIS_ANO = 252

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


def _anualizar_taxa_diaria_percentual(taxa_diaria_pct: float | None) -> Optional[float]:
    """Converte taxa diária em percentual para taxa anualizada em percentual."""
    if taxa_diaria_pct is None:
        return None
    return round(((1 + float(taxa_diaria_pct) / 100) ** _DIAS_UTEIS_ANO - 1) * 100, 4)


def _normalizar_taxa_anual(valor_pct: float | None) -> Optional[float]:
    """
    Normaliza taxa para % a.a.

    Heurística:
    - 0 < valor < 1: taxa diária percentual, anualizar.
    - valor >= 1: já está em percentual anual ou acumulado compatível.
    """
    if valor_pct is None:
        return None
    valor = float(valor_pct)
    if 0 < valor < 1:
        return _anualizar_taxa_diaria_percentual(valor)
    return valor


def coletar_macro(forcar_atualizacao: bool = False) -> dict:
    """Coleta SELIC, CDI e IPCA do BCB e salva no banco."""
    hoje = date.today().isoformat()

    existente = db.buscar_um("SELECT * FROM macro WHERE data = ?", (hoje,))
    if existente and not forcar_atualizacao:
        print(f"[bcb] Macro já coletado para {hoje}")
        return dict(existente)

    selic_bruta = _buscar_valor(URL_BCB_SELIC)
    cdi_bruto = _buscar_valor(URL_BCB_CDI)
    ipca = _buscar_valor(URL_BCB_IPCA)

    selic = _normalizar_taxa_anual(selic_bruta)
    cdi = _normalizar_taxa_anual(cdi_bruto)

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
        f"[bcb] Macro coletado → SELIC: {selic}% a.a. (bruta: {selic_bruta}%) | "
        f"CDI: {cdi}% a.a. (bruta: {cdi_bruto}%) | IPCA: {ipca}%"
    )
    return registro


def corrigir_macro_cdi_diario_gravado() -> dict:
    """
    Corrige registros antigos gravados com CDI/SELIC diário.

    Heurística segura:
    - se selic/cdi estão entre 0 e 1, assume taxa diária percentual e anualiza;
    - não consulta o BCB por registro, evitando travar o paper trading.
    """
    rows = db.buscar_todos("SELECT id, data, selic, cdi FROM macro ORDER BY data")

    corrigidos_cdi = 0
    corrigidos_selic = 0

    for row in rows:
        selic = row["selic"]
        cdi = row["cdi"]
        nova_selic = _normalizar_taxa_anual(selic)
        novo_cdi = _normalizar_taxa_anual(cdi)

        if nova_selic != selic:
            corrigidos_selic += 1
        if novo_cdi != cdi:
            corrigidos_cdi += 1

        if nova_selic != selic or novo_cdi != cdi:
            db.executar(
                "UPDATE macro SET selic = ?, cdi = ? WHERE id = ?",
                (nova_selic, novo_cdi, row["id"]),
            )

    _CACHE_MEMORIA.update({"selic": None, "cdi": None, "ipca": None})
    return {
        "registros_lidos": len(rows),
        "cdi_diario_anualizado": corrigidos_cdi,
        "selic_diaria_anualizada": corrigidos_selic,
    }


def obter_cdi_atual() -> Optional[float]:
    """Retorna o CDI anualizado mais recente disponível no banco."""
    if _CACHE_MEMORIA.get("cdi") is not None:
        return _CACHE_MEMORIA["cdi"]

    hoje = date.today().isoformat()
    row = db.buscar_um(
        "SELECT cdi FROM macro WHERE data <= ? ORDER BY data DESC LIMIT 1",
        (hoje,),
    )
    if row and row["cdi"] is not None:
        cdi = _normalizar_taxa_anual(float(row["cdi"]))
        _CACHE_MEMORIA["cdi"] = cdi
        return cdi

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
        selic = _normalizar_taxa_anual(float(row["selic"]))
        _CACHE_MEMORIA["selic"] = selic
        return selic

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
