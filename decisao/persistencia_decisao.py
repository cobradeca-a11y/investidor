"""
decisao/persistencia_decisao.py

Grava decisões no banco e prepara para avaliação futura (aprendizado).

Evolução profissional:
- mantém compatibilidade com vereditos legados em dict;
- aceita o novo objeto DecisaoFIIA;
- grava payload completo em JSON para auditoria e backtesting;
- auto-migra colunas novas sem apagar histórico.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from banco import db
from sistema import observabilidade

try:
    from decisao.objeto_decisao import DecisaoFIIA
except Exception:  # evita quebrar import em ambientes parcialmente atualizados
    DecisaoFIIA = None  # type: ignore


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
    criado_em         TEXT DEFAULT (datetime('now','localtime')),
    risco             TEXT,
    score_final       REAL,
    preco_teto        REAL,
    payload_json      TEXT
)
"""

def _colunas_decisoes() -> list[str]:
    rows = db.buscar_todos("PRAGMA table_info(decisoes)")
    return [r["name"] for r in rows] if rows else []


def _garantir_tabela() -> None:
    """
    Garante que a tabela decisoes existe e contém as colunas modernas.
    Não apaga histórico salvo.
    Usa migração puramente aditiva para preservar chaves estrangeiras.
    """
    colunas = _colunas_decisoes()

    if not colunas:
        # Tabela não existe, cria do zero
        db.executar(_SCHEMA_V2)
        return

    # Se a tabela existe, adiciona dinamicamente colunas que possam estar faltando
    colunas_v2 = {
        "data_decisao": "TEXT",
        "decisao": "TEXT",
        "motivo": "TEXT",
        "confianca": "TEXT",
        "preco_na_decisao": "REAL",
        "preco_justo": "REAL",
        "preco_entrada": "REAL",
        "margem": "REAL",
        "score_ia": "REAL",
        "ia_status": "TEXT",
        "tom_gestor": "TEXT",
        "travas": "TEXT",
        "riscos_ia": "TEXT",
        "versao_modelo": "TEXT",
        "avaliada": "INTEGER DEFAULT 0",
        "criado_em": "TEXT DEFAULT (datetime('now','localtime'))",
        "risco": "TEXT",
        "score_final": "REAL",
        "preco_teto": "REAL",
        "payload_json": "TEXT",
    }

    migrou = False
    for coluna, tipo in colunas_v2.items():
        if coluna not in colunas:
            try:
                db.executar(f"ALTER TABLE decisoes ADD COLUMN {coluna} {tipo}")
                migrou = True
            except Exception as e:
                print(f"[decisao] Erro ao adicionar coluna {coluna}: {e}")

    if migrou:
        print("[decisao] Colunas adicionadas. Atualizando dados legados...")
        try:
            # Verifica se as colunas de origem existem antes do COALESCE
            colunas_atuais = _colunas_decisoes()
            set_clauses = []
            
            if "data" in colunas_atuais:
                set_clauses.append("data_decisao = COALESCE(data_decisao, data)")
            if "status" in colunas_atuais:
                set_clauses.append("decisao = COALESCE(decisao, status)")
            if "justificativa" in colunas_atuais:
                set_clauses.append("motivo = COALESCE(motivo, justificativa)")
            if "margem_seguranca" in colunas_atuais:
                set_clauses.append("margem = COALESCE(margem, margem_seguranca)")
                
            if set_clauses:
                sql = f"UPDATE decisoes SET {', '.join(set_clauses)}"
                db.executar(sql)
                print("[decisao] Migração de dados legados concluída com sucesso!")
        except Exception as e:
            print(f"[decisao] Erro ao preencher dados legados: {e}")


def _json_seguro(valor: Any) -> str:
    return json.dumps(valor, ensure_ascii=False, default=str)


def _normalizar_veredito(veredito: dict[str, Any]) -> dict[str, Any]:
    """Normaliza dict legado do motor_decisao para persistência."""
    return {
        "ticker": veredito.get("ticker"),
        "data_decisao": veredito.get("data_analise", date.today().isoformat()),
        "decisao": veredito.get("decisao"),
        "motivo": veredito.get("motivo"),
        "confianca": veredito.get("confianca"),
        "preco_na_decisao": veredito.get("preco_atual"),
        "preco_justo": veredito.get("preco_justo"),
        "preco_entrada": veredito.get("preco_entrada"),
        "margem": veredito.get("margem"),
        "score_ia": veredito.get("score_ia"),
        "ia_status": veredito.get("ia_status"),
        "tom_gestor": veredito.get("tom_gestor"),
        "travas": _json_seguro(veredito.get("travas", [])),
        "riscos_ia": _json_seguro(veredito.get("riscos_ia", [])),
        "versao_modelo": veredito.get("versao_modelo", "2.0"),
        "risco": veredito.get("risco"),
        "score_final": veredito.get("score_final"),
        "preco_teto": veredito.get("preco_teto"),
        "payload_json": _json_seguro(veredito),
    }


def _normalizar_objeto_decisao(decisao: Any) -> dict[str, Any]:
    """Normaliza DecisaoFIIA para persistência."""
    payload = decisao.to_dict()
    motivo = "; ".join(payload.get("justificativas", []))
    riscos = payload.get("riscos", [])

    return {
        "ticker": payload.get("ticker"),
        "data_decisao": payload.get("criado_em", date.today().isoformat())[:10],
        "decisao": payload.get("acao"),
        "motivo": motivo,
        "confianca": payload.get("confianca"),
        "preco_na_decisao": payload.get("preco_atual"),
        "preco_justo": payload.get("preco_justo"),
        "preco_entrada": payload.get("preco_teto"),
        "margem": payload.get("margem_seguranca"),
        "score_ia": None,
        "ia_status": payload.get("contexto", {}).get("ia_status"),
        "tom_gestor": payload.get("contexto", {}).get("tom_gestor"),
        "travas": _json_seguro(payload.get("gatilhos_invalidez", [])),
        "riscos_ia": _json_seguro(riscos),
        "versao_modelo": payload.get("versao_modelo", "fiia-decisao-v1"),
        "risco": payload.get("risco"),
        "score_final": payload.get("score_final"),
        "preco_teto": payload.get("preco_teto"),
        "payload_json": _json_seguro(payload),
    }


def gravar(veredito: dict[str, Any]) -> int:
    """
    Grava um veredito legado do motor_decisao no banco.
    Retorna o ID da decisão gravada (-1 em caso de erro).
    """
    _garantir_tabela()
    dados = _normalizar_veredito(veredito)

    try:
        decisao_id = db.inserir("decisoes", dados)
        observabilidade.registrar_evento(
            "INFO",
            "decisao.persistencia",
            "Veredito legado salvo",
            ticker=dados.get("ticker"),
            contexto={"decisao_id": decisao_id, "decisao": dados.get("decisao")},
        )
        print(f"[decisao] OK {dados.get('ticker')} -> {dados.get('decisao')} (id={decisao_id})")
        return decisao_id or -1
    except Exception as erro:
        observabilidade.registrar_erro(
            "decisao.persistencia",
            erro,
            ticker=dados.get("ticker"),
            contexto={"tipo": "veredito_legado"},
        )
        return -1


def gravar_decisao(decisao: Any) -> int:
    """
    Grava uma DecisaoFIIA no banco.
    Mantém payload completo para auditoria futura.
    """
    _garantir_tabela()
    dados = _normalizar_objeto_decisao(decisao)

    try:
        decisao_id = db.inserir("decisoes", dados)
        observabilidade.registrar_evento(
            "INFO",
            "decisao.persistencia",
            "Objeto DecisaoFIIA salvo",
            ticker=dados.get("ticker"),
            contexto={"decisao_id": decisao_id, "decisao": dados.get("decisao")},
        )
        return decisao_id or -1
    except Exception as erro:
        observabilidade.registrar_erro(
            "decisao.persistencia",
            erro,
            ticker=dados.get("ticker"),
            contexto={"tipo": "DecisaoFIIA"},
        )
        return -1


def historico(ticker: str, limite: int = 10) -> list:
    """Retorna as últimas decisões gravadas para um ticker."""
    _garantir_tabela()
    rows = db.buscar_todos(
        """
        SELECT * FROM decisoes
        WHERE ticker = ?
        ORDER BY data_decisao DESC, id DESC
        LIMIT ?
        """,
        (ticker.upper(), limite),
    )
    return [dict(r) for r in rows]


def ultima_decisao(ticker: str) -> dict | None:
    """Retorna a decisão mais recente para o ticker."""
    _garantir_tabela()
    row = db.buscar_um(
        """
        SELECT * FROM decisoes
        WHERE ticker = ?
        ORDER BY data_decisao DESC, id DESC
        LIMIT 1
        """,
        (ticker.upper(),),
    )
    return dict(row) if row else None
