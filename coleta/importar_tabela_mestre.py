"""
coleta/importar_tabela_mestre.py
Importa a tabela mestre ticker B3 ↔ CVM para o SQLite.

Uso:
    python main.py --importar-master tabela_mestre_fiia_fiis_b3_cvm.csv

Objetivo:
- consolidar ticker B3, CNPJ do fundo, CNPJ da classe e códigos CVM;
- criar a base institucional para cruzar CVM, FNET, preço e decisões;
- reduzir dependência de fallback patrimonial.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from banco import db

COLUNAS_ESPERADAS = [
    "ticker_base",
    "ticker_b3_11",
    "fundo_b3",
    "razao_social_b3",
    "duplicidade_ticker_b3",
    "match_metodo",
    "match_score",
    "confianca",
    "id_registro_fundo",
    "cnpj_fundo",
    "codigo_cvm_fundo",
    "tipo_fundo_cvm",
    "denominacao_fundo_cvm",
    "situacao_fundo_cvm",
    "data_registro_fundo",
    "data_cancelamento_fundo",
    "administrador_fundo",
    "gestor_fundo",
    "patrimonio_liq_fundo_cadastro",
    "data_patrimonio_fundo_cadastro",
    "id_registro_classe",
    "cnpj_classe",
    "codigo_cvm_classe",
    "tipo_classe_cvm",
    "denominacao_classe_cvm",
    "situacao_classe_cvm",
    "classificacao_classe",
    "forma_condominio_classe",
    "publico_alvo_classe",
    "patrimonio_liq_classe_cadastro",
    "data_patrimonio_classe_cadastro",
    "auditor_classe",
    "custodiante_classe",
    "cad_fi_match_metodo",
    "cad_fi_cnpj",
    "cad_fi_situacao",
    "cad_fi_classe_anbima",
    "inf_diario_dt_competencia",
    "inf_diario_vl_total",
    "inf_diario_vl_quota",
    "inf_diario_vl_patrim_liq",
    "inf_diario_captc_dia",
    "inf_diario_resg_dia",
    "inf_diario_nr_cotistas",
    "observacao_pendencia",
]

_NUMERICOS = {
    "match_score",
    "patrimonio_liq_fundo_cadastro",
    "patrimonio_liq_classe_cadastro",
    "inf_diario_vl_total",
    "inf_diario_vl_quota",
    "inf_diario_vl_patrim_liq",
    "inf_diario_captc_dia",
    "inf_diario_resg_dia",
}

_INTEIROS = {
    "id_registro_fundo",
    "codigo_cvm_fundo",
    "id_registro_classe",
    "codigo_cvm_classe",
    "inf_diario_nr_cotistas",
}


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalizar_texto(valor: Any) -> str | None:
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto or texto.lower() in {"nan", "none", "null"}:
        return None
    return texto


def _normalizar_float(valor: Any) -> float | None:
    texto = _normalizar_texto(valor)
    if texto is None:
        return None
    texto = texto.replace(".", "").replace(",", ".") if "," in texto else texto
    try:
        return float(texto)
    except ValueError:
        return None


def _normalizar_int(valor: Any) -> int | None:
    numero = _normalizar_float(valor)
    if numero is None:
        return None
    return int(numero)


def _normalizar_linha(row: dict[str, Any], arquivo_origem: str, coletado_em: str) -> dict[str, Any]:
    dados: dict[str, Any] = {}
    for coluna in COLUNAS_ESPERADAS:
        valor = row.get(coluna)
        if coluna in _NUMERICOS:
            dados[coluna] = _normalizar_float(valor)
        elif coluna in _INTEIROS:
            dados[coluna] = _normalizar_int(valor)
        else:
            dados[coluna] = _normalizar_texto(valor)

    ticker = dados.get("ticker_b3_11") or dados.get("ticker_base")
    dados["ticker_b3_11"] = ticker.upper() if isinstance(ticker, str) else ticker
    if isinstance(dados.get("ticker_base"), str):
        dados["ticker_base"] = dados["ticker_base"].upper()

    dados["arquivo_origem"] = arquivo_origem
    dados["coletado_em"] = coletado_em
    dados["payload_json"] = json.dumps(row, ensure_ascii=False)
    return dados


def garantir_tabela() -> None:
    sql = """
    CREATE TABLE IF NOT EXISTS cadastro_fundos_master (
        ticker_base TEXT,
        ticker_b3_11 TEXT PRIMARY KEY,
        fundo_b3 TEXT,
        razao_social_b3 TEXT,
        duplicidade_ticker_b3 TEXT,
        match_metodo TEXT,
        match_score REAL,
        confianca TEXT,
        id_registro_fundo INTEGER,
        cnpj_fundo TEXT,
        codigo_cvm_fundo INTEGER,
        tipo_fundo_cvm TEXT,
        denominacao_fundo_cvm TEXT,
        situacao_fundo_cvm TEXT,
        data_registro_fundo TEXT,
        data_cancelamento_fundo TEXT,
        administrador_fundo TEXT,
        gestor_fundo TEXT,
        patrimonio_liq_fundo_cadastro REAL,
        data_patrimonio_fundo_cadastro TEXT,
        id_registro_classe INTEGER,
        cnpj_classe TEXT,
        codigo_cvm_classe INTEGER,
        tipo_classe_cvm TEXT,
        denominacao_classe_cvm TEXT,
        situacao_classe_cvm TEXT,
        classificacao_classe TEXT,
        forma_condominio_classe TEXT,
        publico_alvo_classe TEXT,
        patrimonio_liq_classe_cadastro REAL,
        data_patrimonio_classe_cadastro TEXT,
        auditor_classe TEXT,
        custodiante_classe TEXT,
        cad_fi_match_metodo TEXT,
        cad_fi_cnpj TEXT,
        cad_fi_situacao TEXT,
        cad_fi_classe_anbima TEXT,
        inf_diario_dt_competencia TEXT,
        inf_diario_vl_total REAL,
        inf_diario_vl_quota REAL,
        inf_diario_vl_patrim_liq REAL,
        inf_diario_captc_dia REAL,
        inf_diario_resg_dia REAL,
        inf_diario_nr_cotistas INTEGER,
        observacao_pendencia TEXT,
        arquivo_origem TEXT,
        coletado_em TEXT NOT NULL,
        payload_json TEXT
    )
    """
    with db.transacao() as conn:
        conn.execute(sql)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_master_cnpj_fundo ON cadastro_fundos_master(cnpj_fundo)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_master_cnpj_classe ON cadastro_fundos_master(cnpj_classe)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_master_codigo_cvm_fundo ON cadastro_fundos_master(codigo_cvm_fundo)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_master_codigo_cvm_classe ON cadastro_fundos_master(codigo_cvm_classe)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_master_confianca ON cadastro_fundos_master(confianca)")


def importar_arquivo(caminho_csv: str | Path) -> dict[str, Any]:
    caminho = Path(caminho_csv)
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho}")

    garantir_tabela()

    coletado_em = _agora_iso()
    total_lido = 0
    importados = 0
    ignorados_sem_ticker = 0
    tickers: set[str] = set()

    with caminho.open("r", encoding="utf-8-sig", newline="") as f:
        leitor = csv.DictReader(f, delimiter=";")
        colunas_arquivo = leitor.fieldnames or []
        faltantes = [c for c in COLUNAS_ESPERADAS if c not in colunas_arquivo]
        if faltantes:
            raise ValueError(f"CSV sem colunas obrigatórias: {faltantes}")

        with db.transacao() as conn:
            for row in leitor:
                total_lido += 1
                dados = _normalizar_linha(row, caminho.name, coletado_em)
                ticker = dados.get("ticker_b3_11")
                if not ticker:
                    ignorados_sem_ticker += 1
                    continue

                colunas = list(dados.keys())
                placeholders = ", ".join("?" for _ in colunas)
                atualizacoes = ", ".join(f"{c}=excluded.{c}" for c in colunas if c != "ticker_b3_11")
                sql = f"""
                    INSERT INTO cadastro_fundos_master ({', '.join(colunas)})
                    VALUES ({placeholders})
                    ON CONFLICT(ticker_b3_11) DO UPDATE SET {atualizacoes}
                """
                conn.execute(sql, [dados[c] for c in colunas])

                # Mantém a tabela básica de FIIs povoada para radar/scheduler.
                conn.execute(
                    """
                    INSERT INTO fiis (ticker, nome, tipo, segmento, ativo)
                    VALUES (?, ?, ?, ?, 1)
                    ON CONFLICT(ticker) DO UPDATE SET
                        nome=COALESCE(excluded.nome, fiis.nome),
                        tipo=COALESCE(excluded.tipo, fiis.tipo),
                        segmento=COALESCE(excluded.segmento, fiis.segmento),
                        ativo=1
                    """,
                    (
                        ticker,
                        dados.get("fundo_b3") or dados.get("denominacao_fundo_cvm"),
                        dados.get("tipo_fundo_cvm"),
                        dados.get("cad_fi_classe_anbima") or dados.get("classificacao_classe"),
                    ),
                )
                importados += 1
                tickers.add(str(ticker))

    return {
        "arquivo": str(caminho),
        "total_lido": total_lido,
        "importados_ou_atualizados": importados,
        "ignorados_sem_ticker": ignorados_sem_ticker,
        "tickers_unicos": len(tickers),
        "tabela": "cadastro_fundos_master",
        "coletado_em": coletado_em,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Importa tabela mestre B3 ↔ CVM para o FIIA")
    parser.add_argument("arquivo", help="Caminho do CSV tabela_mestre_fiia_fiis_b3_cvm.csv")
    args = parser.parse_args()

    print(importar_arquivo(args.arquivo))
