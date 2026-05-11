"""
decisao/persistencia_decisao.py
Grava decisões no banco e prepara para avaliação futura (aprendizado).

Auto-migração: detecta schema antigo da tabela 'decisoes' e atualiza
para v2.0 automaticamente (a tabela fica vazia antes do motor existir).
"""

import json
from datetime import date
from banco import db


_SCHEMA_V2 = """
CREATE TABLE IF NOT EXISTS decisoes (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker            TEXT NOT NULL,
    data_decisao      TEXT NOT NULL,
    decisao           TEXT NOT NULL,
    motivo            TEXT,
    confianca         TEXT,
    preco_na_decisao  REAL,
    preco_justo       REAL,
    preco_entrada     REAL,
    margem            REAL,
    score_ia          REAL,
    ia_status         TEXT,
    tom_gestor        TEXT,
    travas            TEXT,
    riscos_ia         TEXT,
    versao_modelo     TEXT DEFAULT '2.0',
    avaliada          INTEGER DEFAULT 0,
    criado_em         TEXT DEFAULT (datetime('now','localtime'))
)
"""


def _garantir_tabela() -> None:
    """
    Garante que a tabela decisoes existe com o schema v2.0.
    Se encontrar o schema antigo (coluna 'status' em vez de 'decisao'),
    dropa e recria — a tabela estava vazia antes do motor existir.
    """
    rows   = db.buscar_todos("PRAGMA table_info(decisoes)")
    colunas = [r["name"] for r in rows] if rows else []

    if colunas and "data_decisao" not in colunas:
        # Schema antigo detectado — migra
        print("[decisao] Migrando tabela 'decisoes' para schema v2.0...")
        db.executar("DROP TABLE IF EXISTS decisoes")
        colunas = []

    if not colunas:
        db.executar(_SCHEMA_V2)


def gravar(veredito: dict) -> int:
    """
    Grava um veredito do motor_decisao no banco.
    Retorna o ID da decisão gravada (-1 em caso de erro).
    """
    _garantir_tabela()

    dados = {
        "ticker":           veredito.get("ticker"),
        "data_decisao":     veredito.get("data_analise", date.today().isoformat()),
        "decisao":          veredito.get("decisao"),
        "motivo":           veredito.get("motivo"),
        "confianca":        veredito.get("confianca"),
        "preco_na_decisao": veredito.get("preco_atual"),
        "preco_justo":      veredito.get("preco_justo"),
        "preco_entrada":    veredito.get("preco_entrada"),
        "margem":           veredito.get("margem"),
        "score_ia":         veredito.get("score_ia"),
        "ia_status":        veredito.get("ia_status"),
        "tom_gestor":       veredito.get("tom_gestor"),
        "travas":           json.dumps(veredito.get("travas", []), ensure_ascii=False),
        "riscos_ia":        json.dumps(veredito.get("riscos_ia", []), ensure_ascii=False),
        "versao_modelo":    veredito.get("versao_modelo", "2.0"),
    }

    decisao_id = db.inserir("decisoes", dados)
    print(
        f"[decisao] OK {veredito.get('ticker')} -> "
        f"{veredito.get('decisao')} (id={decisao_id})"
    )
    return decisao_id or -1


def historico(ticker: str, limite: int = 10) -> list:
    """Retorna as últimas decisões gravadas para um ticker."""
    _garantir_tabela()
    rows = db.buscar_todos(
        """
        SELECT * FROM decisoes
        WHERE ticker = ?
        ORDER BY data_decisao DESC
        LIMIT ?
        """,
        (ticker, limite)
    )
    return [dict(r) for r in rows]


def ultima_decisao(ticker: str) -> dict | None:
    """Retorna a decisão mais recente para o ticker."""
    _garantir_tabela()
    row = db.buscar_um(
        "SELECT * FROM decisoes WHERE ticker = ? ORDER BY data_decisao DESC LIMIT 1",
        (ticker,)
    )
    return dict(row) if row else None
