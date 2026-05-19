"""
decisao/auditoria_decisao.py

Serviço de consulta auditável de decisões salvas.

Regras:
- consulta somente banco local de decisões persistidas;
- não dispara motor de decisão;
- não dispara scraping/coleta;
- replay é opcional e explícito;
- retorna payload normalizado e validação de hash sem expor stacktrace.
"""
from __future__ import annotations

from typing import Any

from banco import db
from decisao.persistencia_decisao import validar_payload_salvo, replay_decisao_salva


def _row_para_dict(row: Any) -> dict[str, Any] | None:
    if not row:
        return None
    return dict(row)


def _resumo_registro(registro: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": registro.get("id"),
        "ticker": registro.get("ticker"),
        "data_decisao": registro.get("data_decisao"),
        "decisao": registro.get("decisao"),
        "motivo": registro.get("motivo"),
        "confianca": registro.get("confianca"),
        "risco": registro.get("risco"),
        "score_final": registro.get("score_final"),
        "preco_na_decisao": registro.get("preco_na_decisao"),
        "preco_justo": registro.get("preco_justo"),
        "preco_entrada": registro.get("preco_entrada"),
        "margem": registro.get("margem"),
        "payload_hash": registro.get("payload_hash"),
        "contexto_versao": registro.get("contexto_versao"),
        "versao_motor": registro.get("versao_motor") or registro.get("versao_modelo"),
    }


def buscar_decisao_salva(decisao_id: int) -> dict[str, Any] | None:
    """Busca decisão por ID sem acionar coleta, scraping ou motor."""
    row = db.buscar_um("SELECT * FROM decisoes WHERE id = ?", (decisao_id,))
    return _row_para_dict(row)


def listar_decisoes_auditaveis(limite: int = 50) -> dict[str, Any]:
    """Lista decisões com metadados de auditoria, sem retornar payload completo."""
    limite_seguro = max(1, min(int(limite or 50), 500))
    rows = db.buscar_todos(
        """
        SELECT * FROM decisoes
        ORDER BY data_decisao DESC, id DESC
        LIMIT ?
        """,
        (limite_seguro,),
    )

    itens = []
    for row in rows:
        registro = dict(row)
        validacao = validar_payload_salvo(registro)
        itens.append({
            **_resumo_registro(registro),
            "hash_valido": validacao.get("valido", False),
            "payload_hash_calculado": validacao.get("payload_hash_calculado"),
        })

    return {
        "status": "ok",
        "quantidade": len(itens),
        "decisoes": itens,
    }


def consultar_decisao_auditavel(
    decisao_id: int,
    *,
    incluir_payload: bool = True,
    replay: bool = False,
) -> dict[str, Any]:
    """
    Consulta decisão salva, valida payload e opcionalmente executa replay auditável.

    O replay não reexecuta scraping nem motor decisório; apenas reconstrói a
    decisão a partir do payload salvo e compara os hashes.
    """
    registro = buscar_decisao_salva(decisao_id)
    if not registro:
        return {
            "status": "nao_encontrado",
            "mensagem": "Decisão não encontrada.",
            "decisao_id": decisao_id,
        }

    validacao = validar_payload_salvo(registro)
    resposta: dict[str, Any] = {
        "status": "ok",
        "decisao": _resumo_registro(registro),
        "auditoria": {
            "payload_hash_salvo": validacao.get("payload_hash_salvo"),
            "payload_hash_calculado": validacao.get("payload_hash_calculado"),
            "hash_valido": validacao.get("valido", False),
            "contexto_versao": validacao.get("contexto_versao"),
            "versao_motor": validacao.get("versao_motor"),
        },
        "replay": {
            "executado": False,
            "solicitado": bool(replay),
        },
    }

    if incluir_payload:
        resposta["payload"] = validacao.get("payload")

    if replay:
        replay_resultado = replay_decisao_salva(decisao_id)
        hash_salvo = replay_resultado.get("payload_hash_salvo")
        hash_replay = replay_resultado.get("payload_hash_replay")
        resposta["replay"] = {
            "executado": True,
            "status": replay_resultado.get("status"),
            "replay_deterministico": replay_resultado.get("replay_deterministico", False),
            "divergencia_replay": bool(hash_salvo and hash_replay and hash_salvo != hash_replay),
            "payload_hash_salvo": hash_salvo,
            "payload_hash_replay": hash_replay,
            "fonte_replay": replay_resultado.get("fonte_replay"),
        }
        if replay_resultado.get("status") != "ok":
            resposta["replay"]["mensagem"] = "Replay não validado para o payload salvo."

    return resposta
