"""
coleta/cvm_coletores.py
Coletores CVM para o FIIA — versão produção.

Funções:
- baixar ZIPs oficiais da CVM;
- persistir informes mensais, trimestrais, anuais e DFIN;
- normalizar CNPJs;
- filtrar apenas fundos presentes em cadastro_fundos_master;
- extrair links FNET disponíveis nos informes anuais;
- sincronizar indicadores CVM recentes na tabela mestre.
"""
from __future__ import annotations

import io
import logging
import re
import sqlite3
import zipfile
from datetime import date, datetime
from typing import Any

import pandas as pd
import requests

logger = logging.getLogger(__name__)
HEADERS = {"User-Agent": "FIIA/1.0"}

URL_MENSAL = "https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_{ano}.zip"
URL_TRIMESTRAL = "https://dados.cvm.gov.br/dados/FII/DOC/INF_TRIMESTRAL/DADOS/inf_trimestral_fii_{ano}.zip"
URL_ANUAL = "https://dados.cvm.gov.br/dados/FII/DOC/INF_ANUAL/DADOS/inf_anual_fii_{ano}.zip"
URL_DFIN = "https://dados.cvm.gov.br/dados/FII/DOC/DFIN/DADOS/dfin_fii_{ano}.csv"

TABELAS_MENSAL = {
    "ativo_passivo": "cvm_mensal_ativo_passivo",
    "complemento": "cvm_mensal_complemento",
    "geral": "cvm_mensal_geral",
}

TABELAS_TRIMESTRAL = {
    "alienacao_imovel": "cvm_tri_alienacao_imovel",
    "alienacao_terreno": "cvm_tri_alienacao_terreno",
    "aquisicao_imovel": "cvm_tri_aquisicao_imovel",
    "aquisicao_terreno": "cvm_tri_aquisicao_terreno",
    "ativo": "cvm_tri_ativo",
    "ativo_garantia_rentabilidade": "cvm_tri_ativo_garantia",
    "complemento": "cvm_tri_complemento",
    "direito": "cvm_tri_direito",
    "geral": "cvm_tri_geral",
    "imovel": "cvm_tri_imovel",
    "imovel_desempenho": "cvm_tri_imovel_desempenho",
    "imovel_renda_acabado_contrato": "cvm_tri_imovel_contrato",
    "imovel_renda_acabado_inquilino": "cvm_tri_imovel_inquilino",
    "rentabilidade_efetiva": "cvm_tri_rentabilidade",
    "resultado_contabil_financeiro": "cvm_tri_resultado",
    "terreno": "cvm_tri_terreno",
}

TABELAS_ANUAL = {
    "ativo_adquirido": "cvm_anual_ativo_adquirido",
    "ativo_transacao": "cvm_anual_ativo_transacao",
    "ativo_valor_contabil": "cvm_anual_ativo_valor_contabil",
    "complemento": "cvm_anual_complemento",
    "diretor_responsavel": "cvm_anual_diretor",
    "distribuicao_cotistas": "cvm_anual_distribuicao_cotistas",
    "experiencia_profissional": "cvm_anual_experiencia",
    "geral": "cvm_anual_geral",
    "prestador_servico": "cvm_anual_prestador",
    "processo": "cvm_anual_processo",
    "processo_semelhante": "cvm_anual_processo_semelhante",
    "representante_cotista": "cvm_anual_representante",
}


def _conectar(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _normalizar_cnpj(serie: pd.Series) -> pd.Series:
    return serie.fillna("").astype(str).str.replace(r"\D", "", regex=True).str.zfill(14)


def _cnpjs_alvo(conn: sqlite3.Connection) -> set[str]:
    try:
        df = pd.read_sql(
            """
            SELECT cnpj_fundo, cnpj_classe
            FROM cadastro_fundos_master
            WHERE (cnpj_fundo IS NOT NULL AND cnpj_fundo != '')
               OR (cnpj_classe IS NOT NULL AND cnpj_classe != '')
            """,
            conn,
        )
    except Exception:
        logger.warning("cadastro_fundos_master não existe ou está vazia; nenhum CNPJ-alvo carregado")
        return set()

    cnpjs: set[str] = set()
    for coluna in ["cnpj_fundo", "cnpj_classe"]:
        if coluna in df.columns:
            cnpjs.update(v for v in _normalizar_cnpj(df[coluna]).tolist() if v and v != "00000000000000")
    return cnpjs


def _baixar_zip(url: str) -> zipfile.ZipFile | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=60)
        if resp.status_code == 404:
            logger.warning("404: %s", url)
            return None
        resp.raise_for_status()
        return zipfile.ZipFile(io.BytesIO(resp.content))
    except Exception as erro:
        logger.error("Erro download %s: %s", url, erro)
        return None


def _ler_csv_zip(zf: zipfile.ZipFile, nome: str) -> pd.DataFrame | None:
    try:
        with zf.open(nome) as f:
            return pd.read_csv(f, sep=";", encoding="ISO-8859-1", dtype=str, low_memory=False)
    except Exception as erro:
        logger.error("Erro lendo %s: %s", nome, erro)
        return None


def _sufixo(nome_arquivo: str, ano: int) -> str:
    base = nome_arquivo.replace(".csv", "")
    base = base.replace(f"_{ano}", "")
    for prefixo in ["inf_mensal_fii_", "inf_trimestral_fii_", "inf_anual_fii_"]:
        base = base.replace(prefixo, "")
    return base


def _col_cnpj(df: pd.DataFrame) -> str | None:
    for c in df.columns:
        nome = c.lower()
        if "cnpj" in nome and ("fundo" in nome or "classe" in nome):
            return c
    for c in df.columns:
        if "cnpj" in c.lower():
            return c
    return None


def _salvar(df: pd.DataFrame, tabela: str, conn: sqlite3.Connection, if_exists: str = "append") -> int:
    if df.empty:
        return 0
    df = df.copy()
    df["data_ingestao"] = datetime.now().isoformat()
    df.to_sql(tabela, conn, if_exists=if_exists, index=False)
    logger.info("  [%s] +%s registros", tabela, len(df))
    return len(df)


def _processar_zip(
    zf: zipfile.ZipFile,
    mapa_tabelas: dict[str, str],
    cnpjs: set[str],
    conn: sqlite3.Connection,
    ano: int,
) -> int:
    total = 0
    for nome_arq in zf.namelist():
        if not nome_arq.lower().endswith(".csv"):
            continue

        sufixo = _sufixo(nome_arq, ano)
        tabela = mapa_tabelas.get(sufixo)
        if not tabela:
            logger.debug("Sufixo sem mapeamento: %s (%s)", sufixo, nome_arq)
            continue

        df = _ler_csv_zip(zf, nome_arq)
        if df is None or df.empty:
            continue

        col = _col_cnpj(df)
        if col:
            df[col] = _normalizar_cnpj(df[col])
            if cnpjs:
                df = df[df[col].isin(cnpjs)]

        if df.empty:
            logger.debug("%s: 0 linhas após filtro", nome_arq)
            continue

        total += _salvar(df, tabela, conn)

    return total


def _tabela_existe(conn: sqlite3.Connection, tabela: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (tabela,)).fetchone()
    return row is not None


def _colunas(conn: sqlite3.Connection, tabela: str) -> set[str]:
    if not _tabela_existe(conn, tabela):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({tabela})").fetchall()}


def _primeira_coluna_existente(conn: sqlite3.Connection, tabela: str, candidatas: list[str]) -> str | None:
    existentes = _colunas(conn, tabela)
    for coluna in candidatas:
        if coluna in existentes:
            return coluna
    return None


def coletar_mensal(db_path: str = "fiia.db", ano: int | None = None) -> int:
    ano = ano or date.today().year
    url = URL_MENSAL.format(ano=ano)
    logger.info("INF_MENSAL %s: %s", ano, url)

    zf = _baixar_zip(url)
    if not zf:
        return 0

    conn = _conectar(db_path)
    try:
        cnpjs = _cnpjs_alvo(conn)
        total = _processar_zip(zf, TABELAS_MENSAL, cnpjs, conn, ano)
        logger.info("INF_MENSAL %s: %s linhas gravadas", ano, total)
        return total
    finally:
        conn.close()


def coletar_trimestral(db_path: str = "fiia.db", ano: int | None = None) -> int:
    ano = ano or date.today().year
    url = URL_TRIMESTRAL.format(ano=ano)
    logger.info("INF_TRIMESTRAL %s: %s", ano, url)

    zf = _baixar_zip(url)
    if not zf:
        return 0

    conn = _conectar(db_path)
    try:
        cnpjs = _cnpjs_alvo(conn)
        total = _processar_zip(zf, TABELAS_TRIMESTRAL, cnpjs, conn, ano)
        logger.info("INF_TRIMESTRAL %s: %s linhas gravadas", ano, total)
        return total
    finally:
        conn.close()


def coletar_anual(db_path: str = "fiia.db", ano: int | None = None) -> int:
    ano = ano or (date.today().year - 1)
    url = URL_ANUAL.format(ano=ano)
    logger.info("INF_ANUAL %s: %s", ano, url)

    zf = _baixar_zip(url)
    if not zf:
        return 0

    conn = _conectar(db_path)
    try:
        cnpjs = _cnpjs_alvo(conn)
        total = _processar_zip(zf, TABELAS_ANUAL, cnpjs, conn, ano)
        logger.info("INF_ANUAL %s: %s linhas gravadas", ano, total)
        return total
    finally:
        conn.close()


def coletar_dfin(db_path: str = "fiia.db", ano: int | None = None) -> int:
    ano = ano or date.today().year
    url = URL_DFIN.format(ano=ano)
    logger.info("DFIN %s: %s", ano, url)

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 404:
            logger.warning("DFIN %s ainda não disponível", ano)
            return 0
        resp.raise_for_status()

        df = pd.read_csv(io.StringIO(resp.text), sep=";", dtype=str, low_memory=False)
        col = _col_cnpj(df)
        conn = _conectar(db_path)
        try:
            cnpjs = _cnpjs_alvo(conn)
            if col:
                df[col] = _normalizar_cnpj(df[col])
                if cnpjs:
                    df = df[df[col].isin(cnpjs)]
            total = _salvar(df, "cvm_dfin", conn)
            logger.info("DFIN %s: %s linhas gravadas", ano, total)
            return total
        finally:
            conn.close()
    except Exception as erro:
        logger.error("Erro DFIN: %s", erro)
        return 0


def extrair_links_fnet(db_path: str = "fiia.db") -> int:
    """Lê cvm_anual_complemento e popula cvm_fnet_documentos_fii com links de download."""
    conn = _conectar(db_path)
    try:
        if not _tabela_existe(conn, "cvm_anual_complemento"):
            logger.warning("cvm_anual_complemento inexistente; rode coletar_anual() antes de extrair FNET")
            return 0

        colunas = _colunas(conn, "cvm_anual_complemento")
        if "Link_Download_Anexo" not in colunas:
            logger.warning("cvm_anual_complemento existe, mas não tem Link_Download_Anexo")
            return 0

        df = pd.read_sql(
            """
            SELECT CNPJ_Fundo_Classe, Data_Referencia, Versao, Link_Download_Anexo
            FROM cvm_anual_complemento
            WHERE Link_Download_Anexo IS NOT NULL AND Link_Download_Anexo != ''
            """,
            conn,
        )

        if df.empty:
            logger.warning("cvm_anual_complemento vazia ou sem links")
            return 0

        df["cnpj_fundo"] = _normalizar_cnpj(df["CNPJ_Fundo_Classe"])
        df["url_documento"] = df["Link_Download_Anexo"].astype(str)
        df["protocolo"] = df["url_documento"].str.extract(r"id=(\d+)", expand=False)
        df["tipo_documento"] = "INF_ANUAL"
        df["categoria"] = "Informe Anual"
        df["assunto"] = "Informe anual CVM/FNET"
        df["fonte"] = "CVM_INF_ANUAL"
        df["arquivo_origem"] = "cvm_anual_complemento"
        df["coletado_em"] = datetime.now().isoformat()
        df["dedupe_key"] = df["cnpj_fundo"].astype(str) + "|" + df["url_documento"].astype(str)

        registros = df[[
            "cnpj_fundo", "categoria", "tipo_documento", "Data_Referencia",
            "url_documento", "protocolo", "assunto", "fonte", "arquivo_origem",
            "coletado_em", "dedupe_key",
        ]].rename(columns={"Data_Referencia": "data_referencia"})

        for row in registros.to_dict(orient="records"):
            conn.execute(
                """
                INSERT OR IGNORE INTO cvm_fnet_documentos_fii
                    (cnpj_fundo, categoria, tipo_documento, data_referencia, url_documento,
                     protocolo, assunto, fonte, arquivo_origem, coletado_em, dedupe_key)
                VALUES
                    (:cnpj_fundo, :categoria, :tipo_documento, :data_referencia, :url_documento,
                     :protocolo, :assunto, :fonte, :arquivo_origem, :coletado_em, :dedupe_key)
                """,
                row,
            )
        conn.commit()
        logger.info("Links FNET extraídos: %s", len(registros))
        return len(registros)
    except Exception as erro:
        logger.error("Erro extrair_links_fnet: %s", erro)
        return 0
    finally:
        conn.close()


def sincronizar_indicadores_master(db_path: str = "fiia.db") -> dict[str, Any]:
    """Atualiza cadastro_fundos_master com campos recentes do informe mensal quando existirem."""
    conn = _conectar(db_path)
    try:
        if not _tabela_existe(conn, "cadastro_fundos_master"):
            return {"sincronizado": False, "erro": "cadastro_fundos_master inexistente"}

        updates: list[str] = []

        if _tabela_existe(conn, "cvm_mensal_ativo_passivo"):
            col_pl = _primeira_coluna_existente(
                conn,
                "cvm_mensal_ativo_passivo",
                ["Patrimonio_Liquido", "Patrimonio_Liq", "Patrimonio_Liquido_Contabil", "PL", "Total_Ativo"],
            )
            if col_pl:
                updates.append(
                    f"""
                    inf_diario_vl_patrim_liq = COALESCE((
                        SELECT a.{col_pl}
                        FROM cvm_mensal_ativo_passivo a
                        WHERE a.CNPJ_Fundo_Classe = REPLACE(REPLACE(REPLACE(m.cnpj_fundo,'.',''),'/',''),'-','')
                        ORDER BY a.Data_Referencia DESC LIMIT 1
                    ), inf_diario_vl_patrim_liq)
                    """
                )

        if _tabela_existe(conn, "cvm_mensal_complemento"):
            col_cotistas = _primeira_coluna_existente(
                conn,
                "cvm_mensal_complemento",
                ["Total_Numero_Cotistas", "Numero_Cotistas", "NR_COTST", "Num_Cotistas"],
            )
            if col_cotistas:
                updates.append(
                    f"""
                    inf_diario_nr_cotistas = COALESCE((
                        SELECT c.{col_cotistas}
                        FROM cvm_mensal_complemento c
                        WHERE c.CNPJ_Fundo_Classe = REPLACE(REPLACE(REPLACE(m.cnpj_fundo,'.',''),'/',''),'-','')
                        ORDER BY c.Data_Referencia DESC LIMIT 1
                    ), inf_diario_nr_cotistas)
                    """
                )

        if not updates:
            return {"sincronizado": False, "erro": "nenhuma coluna CVM compatível encontrada"}

        sql = f"UPDATE cadastro_fundos_master AS m SET {', '.join(updates)}"
        conn.execute(sql)
        conn.commit()
        return {"sincronizado": True, "linhas_afetadas": conn.total_changes, "campos_atualizados": len(updates)}
    except Exception as erro:
        logger.error("Erro sync master: %s", erro)
        return {"sincronizado": False, "erro": str(erro)}
    finally:
        conn.close()


def carga_historica(db_path: str = "fiia.db", anos: int = 3) -> dict[str, Any]:
    ano_atual = date.today().year
    totais: dict[str, Any] = {"mensal": 0, "trimestral": 0, "anual": 0, "dfin": 0, "links_fnet": 0}

    for i in range(anos):
        ano = ano_atual - i
        totais["mensal"] += coletar_mensal(db_path, ano=ano)
        totais["trimestral"] += coletar_trimestral(db_path, ano=ano)
        if ano < ano_atual:
            totais["anual"] += coletar_anual(db_path, ano=ano)

    totais["dfin"] = coletar_dfin(db_path, ano=ano_atual)
    totais["links_fnet"] = extrair_links_fnet(db_path)
    totais["sync_master"] = sincronizar_indicadores_master(db_path)
    return totais


def carga_corrente(db_path: str = "fiia.db") -> dict[str, Any]:
    """Carga operacional corrente; inclui anual anterior para habilitar extração FNET."""
    ano_atual = date.today().year
    resultado: dict[str, Any] = {
        "mensal": coletar_mensal(db_path, ano=ano_atual),
        "trimestral": coletar_trimestral(db_path, ano=ano_atual),
        "anual": coletar_anual(db_path, ano=ano_atual - 1),
        "dfin": coletar_dfin(db_path, ano=ano_atual),
    }
    resultado["links_fnet"] = extrair_links_fnet(db_path)
    resultado["sync_master"] = sincronizar_indicadores_master(db_path)
    return resultado


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print("=== CARGA HISTÓRICA CVM (3 anos) ===")
    print(carga_historica(anos=3))
