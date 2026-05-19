"""
aprendizado/ajustes_pesos.py

Sugestões controladas de ajuste de pesos do FIIA.

Regras:
- nenhuma sugestão é aplicada automaticamente;
- toda sugestão contém evidência, amostra, período e impacto estimado;
- não altera thresholds dos gates;
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
            criado_em TEXT NOT NULL,
            CHECK(tipo_sugestao IN ('REDUZIR_PESO', 'AUMENTAR_PESO', 'REVISAR_REGRA', 'MANTER_SEM_ALTERACAO'))
        )
        """
    )
    db.executar(
        f"CREATE INDEX IF NOT EXISTS idx_{TABELA_SUGESTOES_AJUSTE}_regra ON {TABELA_SUGESTOES_AJUSTE}(regra)"
    )
    db.executar(
        f"CREATE INDEX IF NOT EXISTS idx_{TABELA_SUGESTOES_AJUSTE}_aplicado ON {TABELA_SUGESTOES_AJUSTE}(aplicado)"
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
             requer_aprovacao_humana, criado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                registro["criado_em"],
            ),
        )
    return registro


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
