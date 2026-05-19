"""
decisao/persistencia_decisao.py

Grava decisões no banco e prepara para avaliação futura (aprendizado).

Evolução profissional:
- mantém compatibilidade com vereditos legados em dict;
- aceita o novo objeto DecisaoFIIA;
- grava payload completo em JSON para auditoria e backtesting;
- grava hash SHA-256 verificável do payload normalizado;
- persiste versão do contexto e versão do motor;
- permite replay auditável sem coletar dados novos;
- auto-migra colunas novas sem apagar histórico.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any

from banco import db
from sistema import observabilidade
from decisao.objeto_decisao import normalizar_contrato_decisao

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
    payload_json      TEXT,
    payload_hash      TEXT,
    contexto_versao   TEXT,
    versao_motor      TEXT
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
        db.executar(_SCHEMA_V2)
        return

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
        "payload_hash": "TEXT",
        "contexto_versao": "TEXT",
        "versao_motor": "TEXT",
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
            if "versao_modelo" in colunas_atuais:
                set_clauses.append("versao_motor = COALESCE(versao_motor, versao_modelo)")

            if set_clauses:
                sql = f"UPDATE decisoes SET {', '.join(set_clauses)}"
                db.executar(sql)
                print("[decisao] Migração de dados legados concluída com sucesso!")
        except Exception as e:
            print(f"[decisao] Erro ao preencher dados legados: {e}")


def _json_normalizado(valor: Any) -> str:
    """Serializa JSON com ordenação estável para auditoria e hash."""
    return json.dumps(
        valor,
        ensure_ascii=False,
        default=str,
        sort_keys=True,
        separators=(",", ":"),
    )


def _hash_payload_json(payload_json: str) -> str:
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def _json_seguro(valor: Any) -> str:
    """Serialização estável para campos JSON auxiliares."""
    return _json_normalizado(valor)


def _versao_motor(payload: dict[str, Any]) -> str | None:
    return (
        payload.get("versao_motor")
        or payload.get("versao_modelo")
        or payload.get("modelo_versao")
    )


def _contexto_versao(payload: dict[str, Any]) -> str | None:
    contexto = payload.get("contexto") if isinstance(payload.get("contexto"), dict) else {}
    return payload.get("contexto_versao") or contexto.get("contexto_versao")


def _contexto_do_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    contexto = payload.get("contexto")
    return contexto if isinstance(contexto, dict) else None


def _campos_auditoria(payload: dict[str, Any]) -> dict[str, str | None]:
    """
    Prepara o payload canônico auditável.

    O hash é sempre calculado sobre o payload_json normalizado, com chaves em
    ordem estável. Esses campos permitem reconstruir e validar a decisão salva.
    """
    payload_normalizado = normalizar_contrato_decisao(payload, _contexto_do_payload(payload))
    payload_json = _json_normalizado(payload_normalizado)
    return {
        "payload_json": payload_json,
        "payload_hash": _hash_payload_json(payload_json),
        "contexto_versao": _contexto_versao(payload_normalizado),
        "versao_motor": _versao_motor(payload_normalizado),
    }


def _normalizar_veredito(veredito: dict[str, Any]) -> dict[str, Any]:
    """Normaliza dict legado do motor_decisao para persistência."""
    payload = normalizar_contrato_decisao(veredito, _contexto_do_payload(veredito))
    auditoria = _campos_auditoria(payload)
    return {
        "ticker": payload.get("ticker"),
        "data_decisao": payload.get("data_analise", date.today().isoformat()),
        "decisao": payload.get("decisao"),
        "motivo": payload.get("motivo"),
        "confianca": payload.get("confianca"),
        "preco_na_decisao": payload.get("preco_atual"),
        "preco_justo": payload.get("preco_justo"),
        "preco_entrada": payload.get("preco_entrada"),
        "margem": payload.get("margem"),
        "score_ia": payload.get("score_ia"),
        "ia_status": payload.get("ia_status"),
        "tom_gestor": payload.get("tom_gestor"),
        "travas": _json_seguro(payload.get("travas", [])),
        "riscos_ia": _json_seguro(payload.get("riscos_ia", [])),
        "versao_modelo": payload.get("versao_modelo", "2.0"),
        "risco": payload.get("risco"),
        "score_final": payload.get("score_final"),
        "preco_teto": payload.get("preco_teto") or payload.get("preco_entrada"),
        **auditoria,
    }


def _normalizar_objeto_decisao(decisao: Any) -> dict[str, Any]:
    """Normaliza DecisaoFIIA para persistência."""
    payload = normalizar_contrato_decisao(decisao.to_dict(), getattr(decisao, "contexto", None))
    motivo = payload.get("motivo") or "; ".join(payload.get("justificativas", []))
    riscos = payload.get("riscos", [])
    auditoria = _campos_auditoria(payload)

    contexto = payload.get("contexto") if isinstance(payload.get("contexto"), dict) else {}
    return {
        "ticker": payload.get("ticker"),
        "data_decisao": payload.get("data_analise") or payload.get("criado_em", date.today().isoformat())[:10],
        "decisao": payload.get("decisao") or payload.get("acao"),
        "motivo": motivo,
        "confianca": payload.get("confianca"),
        "preco_na_decisao": payload.get("preco_atual"),
        "preco_justo": payload.get("preco_justo"),
        "preco_entrada": payload.get("preco_entrada") or payload.get("preco_teto"),
        "margem": payload.get("margem") or payload.get("margem_seguranca"),
        "score_ia": payload.get("score_ia"),
        "ia_status": contexto.get("ia_status"),
        "tom_gestor": contexto.get("tom_gestor"),
        "travas": _json_seguro(payload.get("gatilhos_invalidez", [])),
        "riscos_ia": _json_seguro(riscos),
        "versao_modelo": payload.get("versao_modelo", "fiia-decisao-v1"),
        "risco": payload.get("risco"),
        "score_final": payload.get("score_final"),
        "preco_teto": payload.get("preco_teto"),
        **auditoria,
    }


def validar_payload_salvo(registro: dict[str, Any]) -> dict[str, Any]:
    """
    Valida um registro de decisão já carregado do banco.

    Retorna o payload reconstruído, o hash calculado e se ele confere com o
    hash persistido. Não altera banco nem executa coleta.
    """
    payload_json = registro.get("payload_json") or ""
    payload_hash_salvo = registro.get("payload_hash")
    hash_calculado = _hash_payload_json(payload_json) if payload_json else None

    payload = None
    erro = None
    try:
        payload = json.loads(payload_json) if payload_json else None
    except Exception as exc:
        erro = str(exc)

    return {
        "valido": bool(payload_json and payload_hash_salvo and hash_calculado == payload_hash_salvo and erro is None),
        "payload": payload,
        "payload_hash_salvo": payload_hash_salvo,
        "payload_hash_calculado": hash_calculado,
        "contexto_versao": registro.get("contexto_versao") or (payload or {}).get("contexto_versao"),
        "versao_motor": registro.get("versao_motor") or (payload or {}).get("versao_motor") or (payload or {}).get("versao_modelo"),
        "erro": erro,
    }


def reconstruir_validar_payload_salvo(decisao_id: int) -> dict[str, Any]:
    """
    Reconstrói e valida uma decisão persistida pelo ID.

    Esta função é o ponto de auditoria: a decisão salva pode ser reaberta,
    ter seu payload normalizado reconstituído e seu hash verificado.
    """
    _garantir_tabela()
    row = db.buscar_um("SELECT * FROM decisoes WHERE id = ?", (decisao_id,))
    if not row:
        return {
            "valido": False,
            "payload": None,
            "payload_hash_salvo": None,
            "payload_hash_calculado": None,
            "contexto_versao": None,
            "versao_motor": None,
            "erro": "Decisão não encontrada.",
        }
    return validar_payload_salvo(dict(row))


def replay_decisao_salva(decisao_id: int) -> dict[str, Any]:
    """
    Reproduz a decisão persistida apenas a partir do payload salvo.

    Não chama motor, não coleta dados, não usa fontes externas e não altera
    banco. O replay é considerado determinístico quando o payload salvo passa
    na validação de hash e a normalização atual reproduz o mesmo hash.
    """
    _garantir_tabela()
    row = db.buscar_um("SELECT * FROM decisoes WHERE id = ?", (decisao_id,))
    if not row:
        return {
            "status": "erro",
            "replay_deterministico": False,
            "decisao_id": decisao_id,
            "erro": "Decisão não encontrada.",
        }

    registro = dict(row)
    validacao = validar_payload_salvo(registro)
    if not validacao["valido"]:
        return {
            "status": "hash_invalido",
            "replay_deterministico": False,
            "decisao_id": decisao_id,
            "validacao": validacao,
            "erro": validacao.get("erro") or "Hash do payload salvo não confere.",
        }

    payload_salvo = validacao["payload"] or {}
    payload_replay = normalizar_contrato_decisao(payload_salvo, _contexto_do_payload(payload_salvo))
    payload_replay_json = _json_normalizado(payload_replay)
    payload_replay_hash = _hash_payload_json(payload_replay_json)

    return {
        "status": "ok",
        "replay_deterministico": payload_replay_hash == validacao["payload_hash_salvo"],
        "decisao_id": decisao_id,
        "ticker": payload_replay.get("ticker") or registro.get("ticker"),
        "decisao": payload_replay.get("decisao") or registro.get("decisao"),
        "data_decisao": registro.get("data_decisao"),
        "payload_replay": payload_replay,
        "payload_hash_salvo": validacao["payload_hash_salvo"],
        "payload_hash_replay": payload_replay_hash,
        "contexto_versao": validacao.get("contexto_versao"),
        "versao_motor": validacao.get("versao_motor"),
        "fonte_replay": "payload_json_persistido",
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
            contexto={
                "decisao_id": decisao_id,
                "decisao": dados.get("decisao"),
                "payload_hash": dados.get("payload_hash"),
                "contexto_versao": dados.get("contexto_versao"),
                "versao_motor": dados.get("versao_motor"),
            },
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
    Mantém payload completo e hash verificável para auditoria futura.
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
            contexto={
                "decisao_id": decisao_id,
                "decisao": dados.get("decisao"),
                "payload_hash": dados.get("payload_hash"),
                "contexto_versao": dados.get("contexto_versao"),
                "versao_motor": dados.get("versao_motor"),
            },
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