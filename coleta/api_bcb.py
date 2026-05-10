"""
coleta/api_bcb.py
Coleta dados macroeconômicos da API oficial do Banco Central do Brasil.
API pública, gratuita, sem autenticação.
"""
import requests
from datetime import date
from typing import Optional
from config.settings import URL_BCB_SELIC, URL_BCB_CDI, URL_BCB_IPCA
from banco import db


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


def coletar_macro() -> dict:
    """
    Coleta SELIC, CDI e IPCA do BCB e salva no banco.
    Retorna dict com os valores ou None em caso de falha.
    """
    hoje = date.today().isoformat()

    # Verifica se já coletou hoje
    existente = db.buscar_um(
        "SELECT * FROM macro WHERE data = ?", (hoje,)
    )
    if existente:
        print(f"[bcb] Macro já coletado para {hoje}")
        return dict(existente)

    selic = _buscar_valor(URL_BCB_SELIC)
    cdi   = _buscar_valor(URL_BCB_CDI)
    ipca  = _buscar_valor(URL_BCB_IPCA)

    if selic is None and cdi is None:
        print("[bcb] Falha na coleta — sem dados disponíveis")
        return {}

    registro = {
        "data":  hoje,
        "selic": selic,
        "cdi":   cdi,
        "ipca":  ipca,
        "ifix":  None,  # será adicionado via yfinance na Fase 2
    }

    db.upsert("macro", registro)
    print(f"[bcb] Macro coletado → SELIC: {selic}% | CDI: {cdi}% | IPCA: {ipca}%")
    return registro


def obter_cdi_atual() -> Optional[float]:
    """
    Retorna o CDI mais recente disponível no banco.
    Coleta do BCB se não houver dado de hoje.
    """
    hoje = date.today().isoformat()
    row = db.buscar_um(
        "SELECT cdi FROM macro WHERE data <= ? ORDER BY data DESC LIMIT 1",
        (hoje,)
    )
    if row and row["cdi"]:
        return row["cdi"]

    # Tenta coletar agora
    dados = coletar_macro()
    return dados.get("cdi")


def obter_selic_atual() -> Optional[float]:
    """Retorna a SELIC mais recente disponível."""
    hoje = date.today().isoformat()
    row = db.buscar_um(
        "SELECT selic FROM macro WHERE data <= ? ORDER BY data DESC LIMIT 1",
        (hoje,)
    )
    if row and row["selic"]:
        return row["selic"]
    dados = coletar_macro()
    return dados.get("selic")

def obter_ipca_atual() -> Optional[float]:
    """Retorna o IPCA (acumulado 12m) mais recente."""
    hoje = date.today().isoformat()
    row = db.buscar_um(
        "SELECT ipca FROM macro WHERE data <= ? ORDER BY data DESC LIMIT 1",
        (hoje,)
    )
    if row and row["ipca"]:
        return row["ipca"]
    dados = coletar_macro()
    return dados.get("ipca")
