"""
aprendizado/tentativa_erro.py

Camada de tentativa e erro operacional do FIIA.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from banco import db
from sistema import observabilidade

TABELA_SIMULACOES = "aprendizado_simulacoes"
TABELA_RESULTADOS = "aprendizado_resultados"
TABELA_AJUSTES = "aprendizado_ajustes_pesos"

ACOES_OFENSIVAS = {"COMPRAR", "COMPRAR_PARCIAL", "COMPRAR_PARCIALMENTE", "APORTAR", "APORTAR_PARCIAL", "MANTER"}
ACOES_DEFENSIVAS = {"EVITAR", "EVITAR_ENTRADA", "MONITORAR", "AGUARDAR", "REDUZIR", "VENDER", "BLOQUEAR_APORTE"}


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_get(row: Any, chave: str, padrao: Any = None) -> Any:
    try:
        return row[chave]
    except Exception:
        return padrao


def _garantir_coluna(nome_tabela: str, nome_coluna: str, definicao: str) -> None:
    try:
        colunas = db.buscar_todos(f"PRAGMA table_info({nome_tabela})")
        existentes = {_row_get(col, "name") for col in colunas}
        if nome_coluna not in existentes:
            db.executar(f"ALTER TABLE {nome_tabela} ADD COLUMN {nome_coluna} {definicao}")
    except Exception as erro:
        observabilidade.registrar_erro(
            "aprendizado.tentativa_erro",
            erro,
            contexto={"funcao": "_garantir_coluna", "tabela": nome_tabela, "coluna": nome_coluna},
        )


def garantir_tabelas() -> None:
    db.executar(
        f"""
        CREATE TABLE IF NOT EXISTS {TABELA_SIMULACOES} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            acao_simulada TEXT NOT NULL,
            decisao_origem TEXT,
            segmento TEXT,
            score_final REAL,
            confianca TEXT,
            risco TEXT,
            fonte_patrimonial TEXT,
            gate55_status TEXT,
            peso_versao TEXT DEFAULT 'base',
            payload_json TEXT,
            criada_em TEXT NOT NULL
        );
        """
    )
    db.executar(
        f"""
        CREATE TABLE IF NOT EXISTS {TABELA_RESULTADOS} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            simulacao_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            janela_dias INTEGER NOT NULL,
            retorno_pct REAL,
            superou_benchmark INTEGER,
            resultado TEXT NOT NULL,
            falso_positivo INTEGER DEFAULT 0,
            falso_negativo INTEGER DEFAULT 0,
            observado_em TEXT NOT NULL,
            observacao TEXT,
            FOREIGN KEY(simulacao_id) REFERENCES {TABELA_SIMULACOES}(id)
        );
        """
    )
    db.executar(
        f"""
        CREATE TABLE IF NOT EXISTS {TABELA_AJUSTES} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            regra TEXT NOT NULL,
            peso_anterior REAL,
            peso_sugerido REAL,
            motivo TEXT NOT NULL,
            evidencia TEXT,
            aplicado INTEGER DEFAULT 0,
            criado_em TEXT NOT NULL
        );
        """
    )
    _garantir_coluna(TABELA_SIMULACOES, "segmento", "TEXT")


def registrar_simulacao(
    *,
    ticker: str,
    acao_simulada: str,
    decisao_origem: str | None = None,
    segmento: str | None = None,
    score_final: float | None = None,
    confianca: str | None = None,
    risco: str | None = None,
    fonte_patrimonial: str | None = None,
    gate55_status: str | None = None,
    peso_versao: str = "base",
    payload_json: str | None = None,
) -> dict[str, Any]:
    garantir_tabelas()
    dados = {
        "ticker": ticker.upper().replace(".SA", ""),
        "acao_simulada": acao_simulada.upper().strip(),
        "decisao_origem": decisao_origem,
        "segmento": segmento,
        "score_final": score_final,
        "confianca": confianca,
        "risco": risco,
        "fonte_patrimonial": fonte_patrimonial,
        "gate55_status": gate55_status,
        "peso_versao": peso_versao,
        "payload_json": payload_json,
        "criada_em": _agora_iso(),
    }
    simulacao_id = db.inserir(TABELA_SIMULACOES, dados)
    dados["id"] = simulacao_id

    observabilidade.registrar_evento(
        "INFO",
        "aprendizado.tentativa_erro",
        "Simulação registrada",
        ticker=dados["ticker"],
        contexto={"simulacao_id": simulacao_id, "acao_simulada": dados["acao_simulada"]},
    )
    return dados


def registrar_resultado(
    *,
    simulacao_id: int,
    janela_dias: int,
    retorno_pct: float | None,
    superou_benchmark: bool | None,
    observacao: str | None = None,
) -> dict[str, Any]:
    garantir_tabelas()
    simulacao = db.buscar_um(f"SELECT * FROM {TABELA_SIMULACOES} WHERE id = ?", (simulacao_id,))
    if not simulacao:
        raise ValueError("Simulação não encontrada.")

    acao = str(simulacao["acao_simulada"] or "").upper()
    acertou = bool(superou_benchmark) if superou_benchmark is not None else (retorno_pct is not None and retorno_pct > 0)

    falso_positivo = int(acao in ACOES_OFENSIVAS and not acertou)
    falso_negativo = int(acao in ACOES_DEFENSIVAS and acertou)

    if falso_positivo:
        resultado = "FALSO_POSITIVO"
    elif falso_negativo:
        resultado = "FALSO_NEGATIVO"
    elif acertou:
        resultado = "ACERTO"
    else:
        resultado = "ERRO"

    dados = {
        "simulacao_id": simulacao_id,
        "ticker": simulacao["ticker"],
        "janela_dias": janela_dias,
        "retorno_pct": retorno_pct,
        "superou_benchmark": int(bool(superou_benchmark)) if superou_benchmark is not None else None,
        "resultado": resultado,
        "falso_positivo": falso_positivo,
        "falso_negativo": falso_negativo,
        "observado_em": _agora_iso(),
        "observacao": observacao,
    }
    resultado_id = db.inserir(TABELA_RESULTADOS, dados)
    dados["id"] = resultado_id

    observabilidade.registrar_evento(
        "INFO",
        "aprendizado.tentativa_erro",
        "Resultado de simulação registrado",
        ticker=simulacao["ticker"],
        contexto={"resultado_id": resultado_id, "resultado": resultado},
    )
    return dados


def resumo_aprendizado(janela_dias: int | None = None) -> dict[str, Any]:
    """Resume acertos e erros evitando inflar simulações únicas quando há múltiplas janelas."""
    garantir_tabelas()
    if janela_dias is None:
        rows = db.buscar_todos(
            f"""
            SELECT r.*
            FROM {TABELA_RESULTADOS} r
            JOIN (
                SELECT simulacao_id, MAX(janela_dias) AS maior_janela
                FROM {TABELA_RESULTADOS}
                GROUP BY simulacao_id
            ) ult ON ult.simulacao_id = r.simulacao_id AND ult.maior_janela = r.janela_dias
            """
        )
    else:
        rows = db.buscar_todos(f"SELECT * FROM {TABELA_RESULTADOS} WHERE janela_dias = ?", (janela_dias,))

    total = len(rows)
    acertos = sum(1 for r in rows if r["resultado"] == "ACERTO")
    falsos_positivos = sum(int(r["falso_positivo"] or 0) for r in rows)
    falsos_negativos = sum(int(r["falso_negativo"] or 0) for r in rows)

    return {
        "janela_dias": janela_dias,
        "total_resultados_considerados": total,
        "total_simulacoes_unicas": len({r["simulacao_id"] for r in rows}) if rows else 0,
        "acertos": acertos,
        "acerto_pct": round(acertos / total, 4) if total else 0,
        "falsos_positivos": falsos_positivos,
        "falsos_negativos": falsos_negativos,
    }


def detectar_deterioracao_regra(min_amostras: int = 10, limite_falso_positivo: float = 0.35) -> list[dict[str, Any]]:
    garantir_tabelas()
    rows = db.buscar_todos(
        f"""
        SELECT
            s.segmento,
            s.peso_versao,
            s.decisao_origem,
            s.gate55_status,
            s.fonte_patrimonial,
            r.janela_dias,
            r.falso_positivo,
            r.falso_negativo,
            r.resultado
        FROM {TABELA_RESULTADOS} r
        JOIN {TABELA_SIMULACOES} s ON s.id = r.simulacao_id
        """
    )

    grupos: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        chave = (
            f"segmento={_row_get(row, 'segmento') or 'INDEFINIDO'}|"
            f"peso={_row_get(row, 'peso_versao') or 'base'}|"
            f"decisao={_row_get(row, 'decisao_origem') or 'N/D'}|"
            f"gate55={_row_get(row, 'gate55_status') or 'N/D'}|"
            f"fonte={_row_get(row, 'fonte_patrimonial') or 'N/D'}|"
            f"janela={_row_get(row, 'janela_dias') or 'N/D'}"
        )
        grupos.setdefault(chave, []).append(dict(row))

    alertas = []
    for regra, itens in grupos.items():
        if len(itens) < min_amostras:
            continue
        fp = sum(int(i.get("falso_positivo") or 0) for i in itens)
        fn = sum(int(i.get("falso_negativo") or 0) for i in itens)
        taxa_fp = fp / len(itens)
        taxa_fn = fn / len(itens)
        if taxa_fp >= limite_falso_positivo:
            alertas.append(
                {
                    "regra": regra,
                    "amostras": len(itens),
                    "falso_positivo_pct": round(taxa_fp, 4),
                    "falso_negativo_pct": round(taxa_fn, 4),
                    "status": "DETERIORACAO_POSSIVEL",
                }
            )
    return alertas


def sugerir_ajuste_peso(regra: str, peso_anterior: float, peso_sugerido: float, motivo: str, evidencia: str | None = None) -> dict[str, Any]:
    garantir_tabelas()
    dados = {
        "regra": regra,
        "peso_anterior": peso_anterior,
        "peso_sugerido": peso_sugerido,
        "motivo": motivo,
        "evidencia": evidencia,
        "aplicado": 0,
        "criado_em": _agora_iso(),
    }
    ajuste_id = db.inserir(TABELA_AJUSTES, dados)
    dados["id"] = ajuste_id
    return dados
