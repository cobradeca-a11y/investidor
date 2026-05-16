"""
coleta/cvm_informe_mensal.py

Conector CVM — Informes Mensais de FIIs.

Objetivo:
- trazer CVM para o núcleo estrutural do FIIA;
- persistir VP/cota, patrimônio líquido, cotistas e competência;
- permitir recalcular P/VP internamente;
- reduzir dependência de Fundamentus para dados patrimoniais;
- versionar reapresentações CVM sem sobrescrever histórico.

Observação:
Os ZIPs públicos da CVM não exigem token CKAN.
"""
from __future__ import annotations

import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from banco import db
from sistema import observabilidade

BASE_URL = "https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_{ano}.zip"
TABELA = "cvm_informes_mensais_fii"

_MAPEAMENTO_COLUNAS = {
    "cnpj_fundo": ["CNPJ_FUNDO", "CNPJ_FUNDO_CLASSE", "CNPJ", "CNPJ_FII"],
    "competencia": ["DT_COMPTC", "DT_REFER", "DATA_REFERENCIA", "COMPETENCIA"],
    "patrimonio_liquido": ["VL_PATRIM_LIQ", "VL_PATRIMONIO_LIQUIDO", "PATRIMONIO_LIQUIDO"],
    "valor_patrimonial_cota": ["VL_PATRIM_COTA", "VL_QUOTA", "VL_COTA", "VALOR_PATRIMONIAL_COTA"],
    "num_cotistas": ["NR_COTST", "NR_COTISTAS", "NUM_COTISTAS"],
    "num_cotas": ["QT_COTAS", "QT_COTA", "QUANTIDADE_COTAS"],
}

_CAMPOS_VERSIONADOS = (
    "patrimonio_liquido",
    "valor_patrimonial_cota",
    "num_cotistas",
    "num_cotas",
    "payload_json",
)


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_get(row: Any, chave: str, padrao: Any = None) -> Any:
    try:
        return row[chave]
    except Exception:
        return padrao


def _garantir_coluna(nome_tabela: str, nome_coluna: str, definicao: str) -> None:
    colunas = db.buscar_todos(f"PRAGMA table_info({nome_tabela})")
    existentes = {_row_get(col, "name") for col in colunas}
    if nome_coluna not in existentes:
        db.executar(f"ALTER TABLE {nome_tabela} ADD COLUMN {nome_coluna} {definicao}")


def garantir_tabela() -> None:
    sql = f"""
    CREATE TABLE IF NOT EXISTS {TABELA} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cnpj_fundo TEXT NOT NULL,
        competencia TEXT NOT NULL,
        versao INTEGER NOT NULL DEFAULT 1,
        reapresentacao INTEGER NOT NULL DEFAULT 0,
        patrimonio_liquido REAL,
        valor_patrimonial_cota REAL,
        num_cotistas INTEGER,
        num_cotas REAL,
        fonte TEXT NOT NULL DEFAULT 'CVM_INF_MENSAL',
        ano INTEGER,
        arquivo_origem TEXT,
        coletado_em TEXT NOT NULL,
        payload_json TEXT,
        UNIQUE(cnpj_fundo, competencia, versao)
    );
    """
    db.executar(sql)
    _garantir_coluna(TABELA, "versao", "INTEGER NOT NULL DEFAULT 1")
    _garantir_coluna(TABELA, "reapresentacao", "INTEGER NOT NULL DEFAULT 0")
    db.executar(f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{TABELA}_versao ON {TABELA}(cnpj_fundo, competencia, versao)")


def _baixar_zip(ano: int) -> bytes:
    url = BASE_URL.format(ano=ano)
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return response.content


def _normalizar_nome_coluna(nome: str) -> str:
    return str(nome).strip().upper()


def _localizar_coluna(df: pd.DataFrame, candidatos: list[str]) -> str | None:
    colunas = {_normalizar_nome_coluna(c): c for c in df.columns}
    for candidato in candidatos:
        chave = _normalizar_nome_coluna(candidato)
        if chave in colunas:
            return colunas[chave]
    return None


def _to_float(valor: Any) -> float | None:
    if valor is None or pd.isna(valor):
        return None
    try:
        if isinstance(valor, str):
            valor = valor.replace(".", "").replace(",", ".")
        return float(valor)
    except Exception:
        return None


def _to_int(valor: Any) -> int | None:
    numero = _to_float(valor)
    return int(numero) if numero is not None else None


def _ler_csv_do_zip(conteudo_zip: bytes) -> list[tuple[str, pd.DataFrame]]:
    arquivos: list[tuple[str, pd.DataFrame]] = []
    with zipfile.ZipFile(io.BytesIO(conteudo_zip)) as zf:
        for nome in zf.namelist():
            if not nome.lower().endswith((".csv", ".txt")):
                continue
            with zf.open(nome) as arquivo:
                try:
                    df = pd.read_csv(arquivo, sep=";", encoding="latin1", dtype=str)
                except Exception:
                    arquivo.seek(0)
                    df = pd.read_csv(arquivo, sep=";", encoding="utf-8", dtype=str)
                arquivos.append((nome, df))
    return arquivos


def _extrair_registros(ano: int, nome_arquivo: str, df: pd.DataFrame) -> list[dict[str, Any]]:
    colunas = {
        campo: _localizar_coluna(df, candidatos)
        for campo, candidatos in _MAPEAMENTO_COLUNAS.items()
    }

    obrigatorias = ["cnpj_fundo", "competencia"]
    if any(colunas.get(campo) is None for campo in obrigatorias):
        observabilidade.registrar_evento(
            "WARNING",
            "coleta.cvm_informe_mensal",
            "Arquivo ignorado por ausência de colunas obrigatórias",
            fonte="CVM",
            contexto={"arquivo": nome_arquivo, "colunas": list(df.columns)},
        )
        return []

    registros: list[dict[str, Any]] = []
    coletado_em = _agora_iso()

    for _, row in df.iterrows():
        cnpj = row.get(colunas["cnpj_fundo"])
        competencia = row.get(colunas["competencia"])

        if not cnpj or not competencia:
            continue

        registro = {
            "cnpj_fundo": str(cnpj).strip(),
            "competencia": str(competencia).strip()[:10],
            "patrimonio_liquido": _to_float(row.get(colunas["patrimonio_liquido"])) if colunas.get("patrimonio_liquido") else None,
            "valor_patrimonial_cota": _to_float(row.get(colunas["valor_patrimonial_cota"])) if colunas.get("valor_patrimonial_cota") else None,
            "num_cotistas": _to_int(row.get(colunas["num_cotistas"])) if colunas.get("num_cotistas") else None,
            "num_cotas": _to_float(row.get(colunas["num_cotas"])) if colunas.get("num_cotas") else None,
            "fonte": "CVM_INF_MENSAL",
            "ano": ano,
            "arquivo_origem": nome_arquivo,
            "coletado_em": coletado_em,
            "payload_json": row.to_json(force_ascii=False),
        }
        registros.append(registro)

    return registros


def _registro_igual(registro: dict[str, Any], existente: dict[str, Any]) -> bool:
    for campo in _CAMPOS_VERSIONADOS:
        if registro.get(campo) != existente.get(campo):
            return False
    return True


def _salvar_registro(registro: dict[str, Any]) -> None:
    """Salva registro CVM mantendo histórico de reapresentações."""
    existente = db.buscar_um(
        f"""
        SELECT * FROM {TABELA}
        WHERE cnpj_fundo = ? AND competencia = ?
        ORDER BY versao DESC
        LIMIT 1
        """,
        (registro["cnpj_fundo"], registro["competencia"]),
    )

    if existente:
        existente_dict = dict(existente)
        if _registro_igual(registro, existente_dict):
            return
        versao = int(existente_dict.get("versao") or 1) + 1
        registro["versao"] = versao
        registro["reapresentacao"] = 1
    else:
        registro["versao"] = 1
        registro["reapresentacao"] = 0

    colunas = ", ".join(registro.keys())
    placeholders = ", ".join("?" for _ in registro)
    sql = f"""
    INSERT OR IGNORE INTO {TABELA} ({colunas})
    VALUES ({placeholders})
    """
    db.executar(sql, tuple(registro.values()))


def _inferir_ano_do_nome(nome: str) -> int | None:
    import re
    match = re.search(r"(20\d{2})", nome)
    return int(match.group(1)) if match else None


def _processar_arquivos(ano: int | None, arquivos: list[tuple[str, pd.DataFrame]]) -> int:
    total = 0
    for nome_arquivo, df in arquivos:
        registros = _extrair_registros(ano or 0, nome_arquivo, df)
        for registro in registros:
            _salvar_registro(registro)
        total += len(registros)
    return total


def importar_zip_local(caminho_zip: str | Path, ano: int | None = None) -> dict[str, Any]:
    """Importa um ZIP de informe mensal já baixado localmente."""
    garantir_tabela()
    caminho = Path(caminho_zip)
    ano_final = ano or _inferir_ano_do_nome(caminho.name)

    try:
        conteudo = caminho.read_bytes()
        arquivos = _ler_csv_do_zip(conteudo)
        total = _processar_arquivos(ano_final, arquivos)
        resumo = {
            "origem": "local",
            "arquivo_zip": str(caminho),
            "ano": ano_final,
            "arquivos": len(arquivos),
            "registros_processados": total,
        }
        observabilidade.registrar_evento(
            "INFO",
            "coleta.cvm_informe_mensal",
            "Importação local concluída",
            fonte="CVM",
            contexto=resumo,
        )
        return resumo
    except Exception as erro:
        observabilidade.registrar_erro(
            "coleta.cvm_informe_mensal",
            erro,
            fonte="CVM",
            contexto={"arquivo_zip": str(caminho), "ano": ano_final},
        )
        return {"origem": "local", "arquivo_zip": str(caminho), "ano": ano_final, "erro": str(erro), "registros": 0}


def coletar_ano(ano: int) -> dict[str, Any]:
    """Baixa e persiste informes mensais de FIIs de um ano."""
    garantir_tabela()

    try:
        conteudo = _baixar_zip(ano)
        arquivos = _ler_csv_do_zip(conteudo)
        total = _processar_arquivos(ano, arquivos)

        resumo = {"origem": "download", "ano": ano, "arquivos": len(arquivos), "registros_processados": total}
        observabilidade.registrar_evento(
            "INFO",
            "coleta.cvm_informe_mensal",
            "Coleta anual concluída",
            fonte="CVM",
            contexto=resumo,
        )
        return resumo

    except Exception as erro:
        observabilidade.registrar_erro(
            "coleta.cvm_informe_mensal",
            erro,
            fonte="CVM",
            contexto={"ano": ano},
        )
        return {"origem": "download", "ano": ano, "erro": str(erro), "registros": 0}


def coletar_anos(anos: list[int]) -> list[dict[str, Any]]:
    return [coletar_ano(ano) for ano in anos]


def ultimo_por_cnpj(cnpj_fundo: str) -> dict[str, Any] | None:
    garantir_tabela()
    row = db.buscar_um(
        f"""
        SELECT * FROM {TABELA}
        WHERE cnpj_fundo = ?
        ORDER BY competencia DESC, versao DESC
        LIMIT 1
        """,
        (cnpj_fundo,),
    )
    return dict(row) if row else None


def historico_versoes(cnpj_fundo: str, competencia: str) -> list[dict[str, Any]]:
    """Retorna todas as versões de uma competência CVM para auditoria."""
    garantir_tabela()
    rows = db.buscar_todos(
        f"""
        SELECT * FROM {TABELA}
        WHERE cnpj_fundo = ? AND competencia = ?
        ORDER BY versao ASC
        """,
        (cnpj_fundo, competencia),
    )
    return [dict(row) for row in rows]
