"""
coleta/cotahist_b3.py

Importador local do COTAHIST B3 para preco e liquidez historicos.
"""
from __future__ import annotations

import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from banco import db

TABELA = "cotacoes_b3"
_TICKER_FII_RE = re.compile(r"^[A-Z0-9]{4}11$")


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def garantir_tabela() -> None:
    db.executar(
        f"""
        CREATE TABLE IF NOT EXISTS {TABELA} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            data TEXT NOT NULL,
            cod_bdi TEXT,
            tipo_mercado TEXT,
            preco_abertura REAL,
            preco_maximo REAL,
            preco_minimo REAL,
            preco_medio REAL,
            preco_fechamento REAL,
            total_negocios INTEGER,
            quantidade_titulos INTEGER,
            volume_financeiro REAL,
            fonte TEXT NOT NULL DEFAULT 'B3_COTAHIST',
            arquivo_origem TEXT,
            coletado_em TEXT NOT NULL,
            UNIQUE(ticker, data)
        )
        """
    )
    db.executar(f"CREATE INDEX IF NOT EXISTS idx_{TABELA}_ticker_data ON {TABELA}(ticker, data)")


def _centavos(valor: str) -> float | None:
    texto = str(valor or "").strip()
    if not texto:
        return None
    try:
        return int(texto) / 100.0
    except ValueError:
        return None


def _inteiro(valor: str) -> int | None:
    texto = str(valor or "").strip()
    if not texto:
        return None
    try:
        return int(texto)
    except ValueError:
        return None


def _data_iso(valor: str) -> str | None:
    texto = str(valor or "").strip()
    if len(texto) != 8:
        return None
    return f"{texto[0:4]}-{texto[4:6]}-{texto[6:8]}"


def parse_linha(linha: str, arquivo_origem: str | None = None) -> dict[str, Any] | None:
    """Parseia uma linha tipo 01 do COTAHIST e retorna apenas FIIs do mercado a vista."""
    if not linha or len(linha) < 188:
        return None
    if linha[0:2] != "01":
        return None

    ticker = linha[12:24].strip().upper()
    tipo_mercado = linha[24:27].strip()
    if tipo_mercado != "010":
        return None
    if not _TICKER_FII_RE.match(ticker):
        return None

    data = _data_iso(linha[2:10])
    preco_fechamento = _centavos(linha[108:121])
    if not data or preco_fechamento is None:
        return None

    return {
        "ticker": ticker,
        "data": data,
        "cod_bdi": linha[10:12].strip(),
        "tipo_mercado": tipo_mercado,
        "preco_abertura": _centavos(linha[56:69]),
        "preco_maximo": _centavos(linha[69:82]),
        "preco_minimo": _centavos(linha[82:95]),
        "preco_medio": _centavos(linha[95:108]),
        "preco_fechamento": preco_fechamento,
        "total_negocios": _inteiro(linha[147:152]),
        "quantidade_titulos": _inteiro(linha[152:170]),
        "volume_financeiro": _centavos(linha[170:188]),
        "fonte": "B3_COTAHIST",
        "arquivo_origem": arquivo_origem,
        "coletado_em": _agora_iso(),
    }


def _salvar_lote(registros: list[dict[str, Any]]) -> None:
    if not registros:
        return
    colunas = list(registros[0].keys())
    placeholders = ", ".join("?" for _ in colunas)
    sql = f"""
        INSERT OR REPLACE INTO {TABELA} ({", ".join(colunas)})
        VALUES ({placeholders})
    """
    valores = [tuple(registro[coluna] for coluna in colunas) for registro in registros]
    with db.transacao() as conn:
        conn.executemany(sql, valores)


def importar_linhas(linhas: Iterable[str], arquivo_origem: str | None = None, lote: int = 5000) -> dict[str, Any]:
    garantir_tabela()
    total_lidas = 0
    total_importadas = 0
    pendentes: list[dict[str, Any]] = []

    for linha in linhas:
        total_lidas += 1
        registro = parse_linha(linha.rstrip("\r\n"), arquivo_origem=arquivo_origem)
        if not registro:
            continue
        pendentes.append(registro)
        if len(pendentes) >= lote:
            _salvar_lote(pendentes)
            total_importadas += len(pendentes)
            pendentes = []

    _salvar_lote(pendentes)
    total_importadas += len(pendentes)

    return {
        "status": "OK",
        "arquivo_origem": arquivo_origem,
        "linhas_lidas": total_lidas,
        "registros_importados": total_importadas,
    }


def importar_txt_local(caminho_txt: str | Path) -> dict[str, Any]:
    caminho = Path(caminho_txt)
    with caminho.open("r", encoding="latin-1", errors="ignore") as arquivo:
        return importar_linhas(arquivo, arquivo_origem=caminho.name)


def importar_zip_local(caminho_zip: str | Path) -> dict[str, Any]:
    caminho = Path(caminho_zip)
    with zipfile.ZipFile(caminho) as zf:
        nomes = [nome for nome in zf.namelist() if nome.upper().endswith(".TXT")]
        if not nomes:
            return {"status": "AUSENTE", "arquivo_zip": str(caminho), "erro": "ZIP sem TXT COTAHIST"}
        nome_txt = nomes[0]
        with zf.open(nome_txt) as bruto:
            linhas = (linha.decode("latin-1", errors="ignore") for linha in bruto)
            resultado = importar_linhas(linhas, arquivo_origem=nome_txt)
        resultado["arquivo_zip"] = str(caminho)
        return resultado


def preco_historico(ticker: str, data_alvo: str) -> float | None:
    garantir_tabela()
    ticker_norm = ticker.upper().replace(".SA", "").strip()
    row = db.buscar_um(
        f"""
        SELECT preco_fechamento
        FROM {TABELA}
        WHERE ticker = ? AND data >= ?
        ORDER BY data ASC
        LIMIT 1
        """,
        (ticker_norm, str(data_alvo)[:10]),
    )
    if not row or row["preco_fechamento"] is None:
        return None
    return float(row["preco_fechamento"])


def liquidez_media(ticker: str, data_referencia: str, janela_dias: int = 60) -> float | None:
    garantir_tabela()
    ticker_norm = ticker.upper().replace(".SA", "").strip()
    row = db.buscar_um(
        f"""
        SELECT AVG(volume_financeiro) AS liquidez
        FROM (
            SELECT volume_financeiro
            FROM {TABELA}
            WHERE ticker = ? AND data <= ? AND volume_financeiro IS NOT NULL
            ORDER BY data DESC
            LIMIT ?
        )
        """,
        (ticker_norm, str(data_referencia)[:10], int(janela_dias)),
    )
    if not row or row["liquidez"] is None:
        return None
    return float(row["liquidez"])
