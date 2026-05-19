"""
aprendizado/ajustes_pesos.py

Sugestões controladas de ajuste de pesos do FIIA.

Regras:
- nenhuma sugestão é aplicada automaticamente;
- toda sugestão contém evidência, amostra, período e impacto estimado;
- aprovação humana muda apenas estado auditável, não motor, gates ou thresholds;
- não altera contrato final da decisão.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from banco import db
from config import settings
from sistema import observabilidade
from aprendizado.resultados import TABELA_RESULTADOS_OPERACIONAIS, garantir_tabela_resultados_operacionais

TABELA_SUGESTOES_AJUSTE = "aprendizado_sugestoes_ajuste_pesos"
TIPOS_SUGESTAO_VALIDOS = {"REDUZIR_PESO", "AUMENTAR_PESO", "REVISAR_REGRA", "MANTER_SEM_ALTERACAO"}
ESTADOS_SUGESTAO = {"PENDENTE", "APROVADA", "REJEITADA", "EXPIRADA"}
ESTADO_PENDENTE = "PENDENTE"
ESTADO_APROVADA = "APROVADA"
ESTADO_REJEITADA = "REJEITADA"
ESTADO_EXPIRADA = "EXPIRADA"


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _data_iso(valor: str | date | datetime | None) -> str:
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    if valor:
        return str(valor)[:10]
    return date.today().isoformat()


def _row_to_dict(row: Any) -> dict[str, Any] | None:
    if not row:
        return None
    if isinstance(row, dict):
        return row
    try:
        return dict(row)
    except Exception:
        return {k: row[k] for k in row.keys()}


def _garantir_coluna(nome_tabela: str, nome_coluna: str, definicao: str) -> None:
    """Migração aditiva para bancos já existentes."""
    try:
        colunas = db.buscar_todos(f"PRAGMA table_info({nome_tabela})")
        existentes = set()
        for coluna in colunas:
            try:
                existentes.add(coluna["name"])
            except Exception:
                existentes.add(coluna[1])
        if nome_coluna not in existentes:
            db.executar(f"ALTER TABLE {nome_tabela} ADD COLUMN {nome_coluna} {definicao}")
    except Exception as erro:
        observabilidade.registrar_erro(
            "aprendizado.ajustes_pesos",
            erro,
            contexto={"funcao": "_garantir_coluna", "tabela": nome_tabela, "coluna": nome_coluna},
        )


def garantir_tabela_sugestoes_ajuste() -> None:
    db.executar(
        f"""
        CREATE TABLE IF NOT EXISTS {TABELA_SUGESTOES_AJUSTE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            regra TEXT NOT NULL,
            tipo_sugestao TEXT NOT NULL,
            peso_atual REAL,
            peso_sugerido REAL,
            evidencia_json TEXT NOT NULL,
            amostra INTEGER NOT NULL,
            periodo_inicio TEXT,
            periodo_fim TEXT,
            impacto_estimado TEXT NOT NULL,
            motivo TEXT NOT NULL,
            aplicado INTEGER NOT NULL DEFAULT 0,
            requer_aprovacao_humana INTEGER NOT NULL DEFAULT 1,
            estado TEXT NOT NULL DEFAULT 'PENDENTE',
            usuario_decisao TEXT,
            origem_decisao TEXT,
            decidido_em TEXT,
            justificativa_decisao TEXT,
            data_expiracao TEXT,
            criado_em TEXT NOT NULL,
            CHECK(tipo_sugestao IN ('REDUZIR_PESO', 'AUMENTAR_PESO', 'REVISAR_REGRA', 'MANTER_SEM_ALTERACAO')),
            CHECK(estado IN ('PENDENTE', 'APROVADA', 'REJEITADA', 'EXPIRADA'))
        )
        """
    )
    _garantir_coluna(TABELA_SUGESTOES_AJUSTE, "estado", "TEXT NOT NULL DEFAULT 'PENDENTE'")
    _garantir_coluna(TABELA_SUGESTOES_AJUSTE, "usuario_decisao", "TEXT")
    _garantir_coluna(TABELA_SUGESTOES_AJUSTE, "origem_decisao", "TEXT")
    _garantir_coluna(TABELA_SUGESTOES_AJUSTE, "decidido_em", "TEXT")
    _garantir_coluna(TABELA_SUGESTOES_AJUSTE, "justificativa_decisao", "TEXT")
    _garantir_coluna(TABELA_SUGESTOES_AJUSTE, "data_expiracao", "TEXT")
    db.executar(
        f"CREATE INDEX IF NOT EXISTS idx_{TABELA_SUGESTOES_AJUSTE}_regra ON {TABELA_SUGESTOES_AJUSTE}(regra)"
    )
    db.executar(
        f"CREATE INDEX IF NOT EXISTS idx_{TABELA_SUGESTOES_AJUSTE}_aplicado ON {TABELA_SUGESTOES_AJUSTE}(aplicado)"
    )
    db.executar(
        f"CREATE INDEX IF NOT EXISTS idx_{TABELA_SUGESTOES_AJUSTE}_estado ON {TABELA_SUGESTOES_AJUSTE}(estado)"
    )


def criar_sugestao_ajuste(
    *,
    regra: str,
    tipo_sugestao: str,
    peso_atual: float | None,
    peso_sugerido: float | None,
    evidencia: dict[str, Any],
    amostra: int,
    periodo_inicio: str | date | datetime | None,
    periodo_fim: str | date | datetime | None,
    impacto_estimado: str,
    motivo: str,
    data_expiracao: str | date | datetime | None = None,
    persistir: bool = True,
) -> dict[str, Any]:
    """Cria sugestão auditável sem aplicar alteração automaticamente."""
    tipo = str(tipo_sugestao or "REVISAR_REGRA").upper().strip()
    if tipo not in TIPOS_SUGESTAO_VALIDOS:
        tipo = "REVISAR_REGRA"
    registro = {
        "regra": regra,
        "tipo_sugestao": tipo,
        "peso_atual": peso_atual,
        "peso_sugerido": peso_sugerido,
        "evidencia": evidencia or {},
        "amostra": int(amostra or 0),
        "periodo_inicio": _data_iso(periodo_inicio) if periodo_inicio else None,
        "periodo_fim": _data_iso(periodo_fim) if periodo_fim else None,
        "impacto_estimado": impacto_estimado or "Impacto não estimado.",
        "motivo": motivo or "Sem motivo informado.",
        "aplicado": False,
        "requer_aprovacao_humana": True,
        "aplica_automaticamente": False,
        "estado": ESTADO_PENDENTE,
        "usuario_decisao": None,
        "origem_decisao": None,
        "decidido_em": None,
        "justificativa_decisao": None,
        "data_expiracao": _data_iso(data_expiracao) if data_expiracao else None,
        "criado_em": _agora_iso(),
    }

    observabilidade.registrar_evento(
        "INFO",
        "aprendizado.ajustes_pesos",
        "Sugestão controlada de ajuste criada",
        contexto={
            "regra": regra,
            "tipo_sugestao": tipo,
            "amostra": registro["amostra"],
            "estado": ESTADO_PENDENTE,
            "aplica_automaticamente": False,
        },
    )

    if persistir:
        garantir_tabela_sugestoes_ajuste()
        db.executar(
            f"""
            INSERT INTO {TABELA_SUGESTOES_AJUSTE}
            (regra, tipo_sugestao, peso_atual, peso_sugerido, evidencia_json, amostra,
             periodo_inicio, periodo_fim, impacto_estimado, motivo, aplicado,
             requer_aprovacao_humana, estado, usuario_decisao, origem_decisao, decidido_em,
             justificativa_decisao, data_expiracao, criado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                registro["regra"],
                registro["tipo_sugestao"],
                registro["peso_atual"],
                registro["peso_sugerido"],
                json.dumps(registro["evidencia"], ensure_ascii=False, sort_keys=True, default=str),
                registro["amostra"],
                registro["periodo_inicio"],
                registro["periodo_fim"],
                registro["impacto_estimado"],
                registro["motivo"],
                0,
                1,
                registro["estado"],
                registro["usuario_decisao"],
                registro["origem_decisao"],
                registro["decidido_em"],
                registro["justificativa_decisao"],
                registro["data_expiracao"],
                registro["criado_em"],
            ),
        )
    return registro


def obter_sugestao(sugestao_id: int) -> dict[str, Any] | None:
    garantir_tabela_sugestoes_ajuste()
    row = db.buscar_um(f"SELECT * FROM {TABELA_SUGESTOES_AJUSTE} WHERE id = ?", (int(sugestao_id),))
    return _row_to_dict(row)


def listar_sugestoes(estado: str | None = None, limite: int = 100) -> list[dict[str, Any]]:
    garantir_tabela_sugestoes_ajuste()
    limite_seguro = max(1, min(int(limite or 100), 500))
    if estado:
        estado_norm = estado.upper().strip()
        rows = db.buscar_todos(
            f"SELECT * FROM {TABELA_SUGESTOES_AJUSTE} WHERE estado = ? ORDER BY criado_em DESC, id DESC LIMIT ?",
            (estado_norm, limite_seguro),
        )
    else:
        rows = db.buscar_todos(
            f"SELECT * FROM {TABELA_SUGESTOES_AJUSTE} ORDER BY criado_em DESC, id DESC LIMIT ?",
            (limite_seguro,),
        )
    return [dict(row) for row in rows]


def _transicionar_estado_sugestao(
    *,
    sugestao_id: int,
    novo_estado: str,
    usuario: str,
    origem: str,
    justificativa: str,
) -> dict[str, Any]:
    garantir_tabela_sugestoes_ajuste()
    estado = novo_estado.upper().strip()
    if estado not in ESTADOS_SUGESTAO:
        raise ValueError("Estado de sugestão inválido.")
    sugestao = obter_sugestao(sugestao_id)
    if not sugestao:
        return {"status": "nao_encontrada", "id": sugestao_id, "alterou_motor": False, "aplicado": False}
    estado_atual = str(sugestao.get("estado") or ESTADO_PENDENTE).upper()
    if estado_atual != ESTADO_PENDENTE:
        return {
            "status": "bloqueado",
            "id": sugestao_id,
            "estado_atual": estado_atual,
            "motivo": "Somente sugestões pendentes podem mudar de estado.",
            "alterou_motor": False,
            "aplicado": False,
        }
    decidido_em = _agora_iso()
    db.executar(
        f"""
        UPDATE {TABELA_SUGESTOES_AJUSTE}
        SET estado = ?, usuario_decisao = ?, origem_decisao = ?, decidido_em = ?,
            justificativa_decisao = ?, aplicado = 0, requer_aprovacao_humana = 1
        WHERE id = ?
        """,
        (estado, usuario, origem, decidido_em, justificativa, int(sugestao_id)),
    )
    observabilidade.registrar_evento(
        "INFO",
        "aprendizado.ajustes_pesos",
        "Estado de sugestão alterado por feedback humano",
        contexto={
            "sugestao_id": int(sugestao_id),
            "estado_anterior": estado_atual,
            "estado_novo": estado,
            "usuario": usuario,
            "origem": origem,
            "alterou_motor": False,
            "aplicado": False,
        },
    )
    return {
        "status": "ok",
        "id": int(sugestao_id),
        "estado_anterior": estado_atual,
        "estado": estado,
        "usuario_decisao": usuario,
        "origem_decisao": origem,
        "decidido_em": decidido_em,
        "justificativa_decisao": justificativa,
        "alterou_motor": False,
        "aplicado": False,
        "motivo": "Feedback humano registrado. Nenhuma regra crítica foi alterada automaticamente.",
    }


def aprovar_sugestao(sugestao_id: int, *, usuario: str, origem: str, justificativa: str) -> dict[str, Any]:
    return _transicionar_estado_sugestao(
        sugestao_id=sugestao_id,
        novo_estado=ESTADO_APROVADA,
        usuario=usuario,
        origem=origem,
        justificativa=justificativa,
    )


def rejeitar_sugestao(sugestao_id: int, *, usuario: str, origem: str, justificativa: str) -> dict[str, Any]:
    return _transicionar_estado_sugestao(
        sugestao_id=sugestao_id,
        novo_estado=ESTADO_REJEITADA,
        usuario=usuario,
        origem=origem,
        justificativa=justificativa,
    )


def expirar_sugestao(sugestao_id: int, *, usuario: str, origem: str, justificativa: str) -> dict[str, Any]:
    return _transicionar_estado_sugestao(
        sugestao_id=sugestao_id,
        novo_estado=ESTADO_EXPIRADA,
        usuario=usuario,
        origem=origem,
        justificativa=justificativa,
    )


def detectar_padroes_de_erro(
    *,
    min_amostras: int | None = None,
    janela_dias: int | None = None,
) -> list[dict[str, Any]]:
    """Agrupa resultados observados para detectar falso positivo/negativo."""
    garantir_tabela_resultados_operacionais()
    minimo = int(min_amostras or settings.APRENDIZADO_AMOSTRAS_MINIMAS)
    if janela_dias is None:
        rows = db.buscar_todos(f"SELECT * FROM {TABELA_RESULTADOS_OPERACIONAIS}")
    else:
        rows = db.buscar_todos(
            f"SELECT * FROM {TABELA_RESULTADOS_OPERACIONAIS} WHERE janela_dias = ?",
            (int(janela_dias),),
        )

    grupos: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        acao = str(row["acao_original"] or "MONITORAR").upper()
        janela = int(row["janela_dias"] or 0)
        regra = f"acao={acao}|janela={janela}"
        grupos.setdefault(regra, []).append(dict(row))

    padroes = []
    for regra, itens in grupos.items():
        amostra = len(itens)
        if amostra < minimo:
            continue
        falsos_positivos = sum(int(item.get("falso_positivo") or 0) for item in itens)
        falsos_negativos = sum(int(item.get("falso_negativo") or 0) for item in itens)
        fp_pct = falsos_positivos / amostra
        fn_pct = falsos_negativos / amostra
        datas = sorted(str(item.get("data_avaliacao") or item.get("data_decisao")) for item in itens if item.get("data_avaliacao") or item.get("data_decisao"))
        padroes.append({
            "regra": regra,
            "amostra": amostra,
            "periodo_inicio": datas[0] if datas else None,
            "periodo_fim": datas[-1] if datas else None,
            "falsos_positivos": falsos_positivos,
            "falsos_positivos_pct": round(fp_pct * 100, 2),
            "falsos_negativos": falsos_negativos,
            "falsos_negativos_pct": round(fn_pct * 100, 2),
            "resultado_predominante": "FALSO_POSITIVO" if fp_pct >= fn_pct else "FALSO_NEGATIVO",
        })
    return padroes


def gerar_sugestoes_controladas(
    *,
    min_amostras: int | None = None,
    janela_dias: int | None = None,
    persistir: bool = True,
) -> list[dict[str, Any]]:
    """Gera sugestões controladas sem aplicar pesos automaticamente."""
    sugestoes = []
    for padrao in detectar_padroes_de_erro(min_amostras=min_amostras, janela_dias=janela_dias):
        if padrao["falsos_positivos_pct"] >= 35:
            sugestoes.append(criar_sugestao_ajuste(
                regra=padrao["regra"],
                tipo_sugestao="REDUZIR_PESO",
                peso_atual=None,
                peso_sugerido=None,
                evidencia=padrao,
                amostra=padrao["amostra"],
                periodo_inicio=padrao["periodo_inicio"],
                periodo_fim=padrao["periodo_fim"],
                impacto_estimado="Reduzir falsos positivos em entradas ofensivas que não superaram benchmark.",
                motivo="Taxa de falso positivo acima do limite de observação operacional.",
                persistir=persistir,
            ))
        elif padrao["falsos_negativos_pct"] >= 35:
            sugestoes.append(criar_sugestao_ajuste(
                regra=padrao["regra"],
                tipo_sugestao="AUMENTAR_PESO",
                peso_atual=None,
                peso_sugerido=None,
                evidencia=padrao,
                amostra=padrao["amostra"],
                periodo_inicio=padrao["periodo_inicio"],
                periodo_fim=padrao["periodo_fim"],
                impacto_estimado="Reduzir falsos negativos em ativos defensivos/monitorados que superaram benchmark.",
                motivo="Taxa de falso negativo acima do limite de observação operacional.",
                persistir=persistir,
            ))
    return sugestoes


def aplicar_sugestao_automaticamente(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Bloqueio explícito: ajustes nunca são aplicados automaticamente."""
    return {
        "status": "bloqueado",
        "aplicado": False,
        "motivo": "Ajustes de pesos exigem aprovação humana e não são aplicados automaticamente.",
    }