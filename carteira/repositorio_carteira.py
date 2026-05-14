"""
carteira/repositorio_carteira.py

Persistência da carteira real do FIIA.

Objetivo:
- registrar operações de compra/venda;
- manter posições por ticker;
- calcular preço médio por custo médio ponderado;
- expor composição atual para política de carteira;
- preparar rebalanceamento e acompanhamento patrimonial.

Método inicial oficial:
- CUSTO_MEDIO_PONDERADO.

Observação:
Este módulo não calcula imposto de renda. Ele guarda base operacional da carteira.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from banco import db
from sistema import observabilidade

TABELA_POSICOES = "carteira_posicoes"
TABELA_OPERACOES = "carteira_operacoes"


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def garantir_tabelas() -> None:
    """Cria tabelas de carteira se ainda não existirem."""
    db.executar(
        f"""
        CREATE TABLE IF NOT EXISTS {TABELA_POSICOES} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL UNIQUE,
            quantidade REAL NOT NULL DEFAULT 0,
            preco_medio REAL NOT NULL DEFAULT 0,
            custo_total REAL NOT NULL DEFAULT 0,
            segmento TEXT,
            atualizado_em TEXT NOT NULL
        );
        """
    )

    db.executar(
        f"""
        CREATE TABLE IF NOT EXISTS {TABELA_OPERACOES} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            tipo TEXT NOT NULL,
            quantidade REAL NOT NULL,
            preco REAL NOT NULL,
            custos REAL NOT NULL DEFAULT 0,
            valor_total REAL NOT NULL,
            data_operacao TEXT NOT NULL,
            origem TEXT DEFAULT 'MANUAL',
            observacao TEXT,
            criado_em TEXT NOT NULL
        );
        """
    )


def obter_posicao(ticker: str) -> dict[str, Any] | None:
    garantir_tabelas()
    row = db.buscar_um(
        f"SELECT * FROM {TABELA_POSICOES} WHERE ticker = ? LIMIT 1",
        (ticker.upper().replace(".SA", ""),),
    )
    return dict(row) if row else None


def listar_posicoes() -> list[dict[str, Any]]:
    garantir_tabelas()
    rows = db.buscar_todos(
        f"""
        SELECT * FROM {TABELA_POSICOES}
        WHERE quantidade > 0
        ORDER BY ticker
        """
    )
    return [dict(row) for row in rows]


def _salvar_posicao(ticker: str, quantidade: float, preco_medio: float, custo_total: float, segmento: str | None = None) -> None:
    dados = {
        "ticker": ticker.upper().replace(".SA", ""),
        "quantidade": quantidade,
        "preco_medio": preco_medio,
        "custo_total": custo_total,
        "segmento": segmento,
        "atualizado_em": _agora_iso(),
    }

    db.executar(
        f"""
        INSERT INTO {TABELA_POSICOES}
            (ticker, quantidade, preco_medio, custo_total, segmento, atualizado_em)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker) DO UPDATE SET
            quantidade = excluded.quantidade,
            preco_medio = excluded.preco_medio,
            custo_total = excluded.custo_total,
            segmento = COALESCE(excluded.segmento, {TABELA_POSICOES}.segmento),
            atualizado_em = excluded.atualizado_em
        """,
        tuple(dados.values()),
    )


def _registrar_operacao(
    *,
    ticker: str,
    tipo: str,
    quantidade: float,
    preco: float,
    custos: float,
    data_operacao: str | None,
    origem: str,
    observacao: str | None,
) -> int | None:
    valor_total = quantidade * preco + custos if tipo == "COMPRA" else quantidade * preco - custos
    criado_em = _agora_iso()
    data_final = data_operacao or criado_em[:10]

    dados = {
        "ticker": ticker.upper().replace(".SA", ""),
        "tipo": tipo,
        "quantidade": quantidade,
        "preco": preco,
        "custos": custos,
        "valor_total": valor_total,
        "data_operacao": data_final,
        "origem": origem,
        "observacao": observacao,
        "criado_em": criado_em,
    }

    return db.inserir(TABELA_OPERACOES, dados)


def registrar_compra(
    ticker: str,
    quantidade: float,
    preco: float,
    *,
    custos: float = 0.0,
    data_operacao: str | None = None,
    segmento: str | None = None,
    origem: str = "MANUAL",
    observacao: str | None = None,
) -> dict[str, Any]:
    """Registra compra e recalcula custo médio ponderado."""
    garantir_tabelas()
    ticker_norm = ticker.upper().replace(".SA", "")

    if quantidade <= 0 or preco <= 0:
        raise ValueError("Quantidade e preço devem ser positivos para compra.")

    atual = obter_posicao(ticker_norm) or {"quantidade": 0.0, "custo_total": 0.0}
    qtd_atual = float(atual.get("quantidade") or 0.0)
    custo_atual = float(atual.get("custo_total") or 0.0)

    valor_compra = quantidade * preco + custos
    nova_qtd = qtd_atual + quantidade
    novo_custo = custo_atual + valor_compra
    novo_pm = novo_custo / nova_qtd if nova_qtd else 0.0

    operacao_id = _registrar_operacao(
        ticker=ticker_norm,
        tipo="COMPRA",
        quantidade=quantidade,
        preco=preco,
        custos=custos,
        data_operacao=data_operacao,
        origem=origem,
        observacao=observacao,
    )
    _salvar_posicao(ticker_norm, nova_qtd, novo_pm, novo_custo, segmento)

    resultado = obter_posicao(ticker_norm) or {}
    resultado["operacao_id"] = operacao_id

    observabilidade.registrar_evento(
        "INFO",
        "carteira.repositorio",
        "Compra registrada",
        ticker=ticker_norm,
        contexto={"operacao_id": operacao_id, "quantidade": quantidade, "preco": preco},
    )
    return resultado


def registrar_venda(
    ticker: str,
    quantidade: float,
    preco: float,
    *,
    custos: float = 0.0,
    data_operacao: str | None = None,
    origem: str = "MANUAL",
    observacao: str | None = None,
) -> dict[str, Any]:
    """Registra venda reduzindo posição pelo custo médio ponderado."""
    garantir_tabelas()
    ticker_norm = ticker.upper().replace(".SA", "")

    if quantidade <= 0 or preco <= 0:
        raise ValueError("Quantidade e preço devem ser positivos para venda.")

    atual = obter_posicao(ticker_norm)
    if not atual or float(atual.get("quantidade") or 0.0) < quantidade:
        raise ValueError("Quantidade vendida maior que posição disponível.")

    qtd_atual = float(atual.get("quantidade") or 0.0)
    preco_medio = float(atual.get("preco_medio") or 0.0)
    nova_qtd = qtd_atual - quantidade
    novo_custo = max(0.0, nova_qtd * preco_medio)
    novo_pm = preco_medio if nova_qtd > 0 else 0.0

    operacao_id = _registrar_operacao(
        ticker=ticker_norm,
        tipo="VENDA",
        quantidade=quantidade,
        preco=preco,
        custos=custos,
        data_operacao=data_operacao,
        origem=origem,
        observacao=observacao,
    )
    _salvar_posicao(ticker_norm, nova_qtd, novo_pm, novo_custo, atual.get("segmento"))

    resultado = obter_posicao(ticker_norm) or {}
    resultado["operacao_id"] = operacao_id

    observabilidade.registrar_evento(
        "INFO",
        "carteira.repositorio",
        "Venda registrada",
        ticker=ticker_norm,
        contexto={"operacao_id": operacao_id, "quantidade": quantidade, "preco": preco},
    )
    return resultado


def resumo_carteira() -> dict[str, Any]:
    """Retorna resumo básico da carteira por custo."""
    posicoes = listar_posicoes()
    custo_total = sum(float(p.get("custo_total") or 0.0) for p in posicoes)

    por_segmento: dict[str, float] = {}
    for pos in posicoes:
        seg = pos.get("segmento") or "INDEFINIDO"
        por_segmento[seg] = por_segmento.get(seg, 0.0) + float(pos.get("custo_total") or 0.0)

    return {
        "quantidade_ativos": len(posicoes),
        "custo_total": round(custo_total, 2),
        "por_segmento": {
            seg: {
                "custo": round(valor, 2),
                "percentual": round(valor / custo_total, 4) if custo_total else 0.0,
            }
            for seg, valor in por_segmento.items()
        },
        "posicoes": posicoes,
    }


def percentual_ativo(ticker: str) -> float:
    """Retorna percentual aproximado do ativo na carteira por custo."""
    resumo = resumo_carteira()
    custo_total = float(resumo.get("custo_total") or 0.0)
    if custo_total <= 0:
        return 0.0
    pos = obter_posicao(ticker)
    if not pos:
        return 0.0
    return round(float(pos.get("custo_total") or 0.0) / custo_total, 4)


def percentual_segmento(segmento: str | None) -> float:
    """Retorna percentual aproximado do segmento na carteira por custo."""
    if not segmento:
        return 0.0
    resumo = resumo_carteira()
    dados = resumo.get("por_segmento", {}).get(segmento)
    return float(dados.get("percentual") or 0.0) if dados else 0.0
