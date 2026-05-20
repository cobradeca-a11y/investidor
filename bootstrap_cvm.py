"""
bootstrap_cvm.py
Bootstrap de infraestrutura CVM para o FIIA.

Executa em sequência:
  1. Importar tabela mestre ticker->CNPJ para o banco
  2. Coletar informes mensais CVM do ano corrente (e opcionalmente do anterior)

Uso:
    python bootstrap_cvm.py
    python bootstrap_cvm.py --anos 2025 2026
    python bootstrap_cvm.py --so-tabela
    python bootstrap_cvm.py --so-cvm --anos 2026

Saída:
    Logs no terminal + resumo final em JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

# ── Garante que o projeto está no path ────────────────────────────────────────
RAIZ = Path(__file__).parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

# ── Tabela mestre ─────────────────────────────────────────────────────────────
_TABELA_MESTRE_PADRAO = RAIZ / "tabela_mestre_fiia_fiis_b3_cvm.csv"


def _passo_tabela_mestre(caminho_csv: Path) -> dict:
    print("\n" + "─" * 60)
    print("PASSO 1 — Importar tabela mestre ticker → CNPJ")
    print("─" * 60)

    if not caminho_csv.exists():
        msg = f"Arquivo não encontrado: {caminho_csv}"
        print(f"[ERRO] {msg}")
        return {"status": "ERRO", "motivo": msg}

    try:
        from coleta.tabela_mestre_fiis import importar_csv, obter_por_ticker
        t0 = time.time()
        resumo = importar_csv(caminho_csv)
        elapsed = time.time() - t0

        if "erro" in resumo:
            print(f"[ERRO] Falha na importação: {resumo['erro']}")
            return {"status": "ERRO", **resumo}

        registros = resumo.get("registros", 0)
        print(f"[OK] {registros} tickers importados em {elapsed:.1f}s")

        # Verificação rápida: amostra de 3 tickers conhecidos
        amostras = ["HGLG11", "KNCR11", "MXRF11"]
        encontrados = []
        for t in amostras:
            item = obter_por_ticker(t)
            if item and item.get("cnpj_fundo"):
                encontrados.append(f"{t}={item['cnpj_fundo']}")
        if encontrados:
            print(f"[OK] Verificação: {', '.join(encontrados)}")
        else:
            print("[AVISO] Nenhum ticker da amostra encontrado — verifique o CSV.")

        return {"status": "OK", "elapsed_s": round(elapsed, 1), **resumo}

    except Exception as e:
        print(f"[ERRO] {e}")
        return {"status": "ERRO", "motivo": str(e)}


# ── Informe mensal CVM ────────────────────────────────────────────────────────

def _passo_cvm(anos: list[int]) -> dict:
    print("\n" + "─" * 60)
    print(f"PASSO 2 — Coletar informes mensais CVM: {anos}")
    print("─" * 60)

    try:
        from coleta.cvm_informe_mensal import coletar_ano, ultimo_por_cnpj
        from coleta.tabela_mestre_fiis import obter_por_ticker

        resultados = []
        total_registros = 0

        for ano in anos:
            print(f"\n  Baixando informes CVM {ano}...")
            t0 = time.time()
            res = coletar_ano(ano)
            elapsed = time.time() - t0

            registros = res.get("registros_processados", 0)
            total_registros += registros

            if "erro" in res:
                print(f"  [ERRO] {ano}: {res['erro']}")
                resultados.append({"ano": ano, "status": "ERRO", "motivo": res["erro"]})
            else:
                print(f"  [OK] {ano}: {registros} registros em {elapsed:.1f}s")
                resultados.append({
                    "ano": ano,
                    "status": "OK",
                    "registros": registros,
                    "elapsed_s": round(elapsed, 1),
                })

        # Verificação: testa resolução patrimonial em 2 tickers
        print("\n  Verificando resolução patrimonial...")
        tickers_teste = ["HGLG11", "KNCR11"]
        for ticker in tickers_teste:
            identidade = obter_por_ticker(ticker)
            if not identidade or not identidade.get("cnpj_fundo"):
                print(f"  [AVISO] {ticker}: sem CNPJ na tabela mestre (rode o Passo 1 primeiro).")
                continue
            cnpj = identidade["cnpj_fundo"]
            informe = ultimo_por_cnpj(cnpj)
            if informe:
                vp = informe.get("valor_patrimonial_cota")
                pl = informe.get("patrimonio_liquido")
                comp = informe.get("competencia", "?")
                print(f"  [OK] {ticker}: VP/cota=R${vp} | PL=R${pl:,.0f} | competência={comp}")
            else:
                print(f"  [AVISO] {ticker}: CNPJ={cnpj} sem informe no banco.")

        return {
            "status": "OK" if all(r["status"] == "OK" for r in resultados) else "PARCIAL",
            "anos": resultados,
            "total_registros": total_registros,
        }

    except Exception as e:
        print(f"[ERRO] {e}")
        return {"status": "ERRO", "motivo": str(e)}


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap CVM do FIIA")
    parser.add_argument(
        "--anos", nargs="+", type=int,
        default=[date.today().year - 1, date.today().year],
        help="Anos a coletar (padrão: ano anterior + ano atual)",
    )
    parser.add_argument("--so-tabela", action="store_true", help="Executa só o Passo 1")
    parser.add_argument("--so-cvm", action="store_true", help="Executa só o Passo 2")
    parser.add_argument(
        "--tabela-csv", type=Path, default=_TABELA_MESTRE_PADRAO,
        help=f"Caminho do CSV da tabela mestre (padrão: {_TABELA_MESTRE_PADRAO})",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("FIIA — Bootstrap CVM")
    print(f"Raiz do projeto: {RAIZ}")
    print(f"Banco: {RAIZ / 'fiia.db'}")
    print("=" * 60)

    t_inicio = time.time()
    resultado: dict = {}

    executar_tabela = not args.so_cvm
    executar_cvm = not args.so_tabela

    if executar_tabela:
        resultado["tabela_mestre"] = _passo_tabela_mestre(args.tabela_csv)

    if executar_cvm:
        resultado["cvm"] = _passo_cvm(sorted(set(args.anos)))

    elapsed_total = time.time() - t_inicio

    print("\n" + "=" * 60)
    print(f"Bootstrap concluído em {elapsed_total:.1f}s")
    print("=" * 60)
    print(json.dumps(resultado, indent=2, ensure_ascii=False))

    # Código de saída: 0 se tudo OK, 1 se qualquer passo falhou
    falhas = [v for v in resultado.values() if v.get("status") not in ("OK",)]
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
