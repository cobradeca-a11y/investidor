from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from coleta.cvm_informe_mensal import importar_zip_local
from banco import db


def _melhor_arquivo(downloads: Path, padrao: str) -> Path | None:
    candidatos = [p for p in downloads.glob(padrao) if p.is_file()]
    if not candidatos:
        return None
    return sorted(candidatos, key=lambda p: (p.stat().st_mtime, p.stat().st_size), reverse=True)[0]


def inventariar(downloads: Path, anos: list[int]) -> dict[str, Any]:
    itens: dict[str, Any] = {
        "downloads": str(downloads),
        "anos": anos,
        "mensal": {},
        "trimestral": {},
        "anual": {},
        "cotahist": {},
        "faltantes_criticos": [],
    }

    for ano in anos:
        mensal = _melhor_arquivo(downloads, f"inf_mensal_fii_{ano}*.zip")
        trimestral = _melhor_arquivo(downloads, f"inf_trimestral_fii_{ano}*.zip")
        anual = _melhor_arquivo(downloads, f"inf_anual_fii_{ano}*.zip")
        cotahist = _melhor_arquivo(downloads, f"COTAHIST_A{ano}.ZIP")

        itens["mensal"][str(ano)] = str(mensal) if mensal else None
        itens["trimestral"][str(ano)] = str(trimestral) if trimestral else None
        itens["anual"][str(ano)] = str(anual) if anual else None
        itens["cotahist"][str(ano)] = str(cotahist) if cotahist else None

        if not cotahist:
            itens["faltantes_criticos"].append(f"COTAHIST_A{ano}.ZIP")

    return itens


def _registros_mensais_existentes(ano: int) -> int:
    row = db.buscar_um(
        "SELECT COUNT(*) AS total FROM cvm_informes_mensais_fii WHERE ano = ?",
        (ano,),
    )
    return int(row["total"] or 0) if row else 0


def importar_mensais(downloads: Path, anos: list[int], force: bool = False) -> list[dict[str, Any]]:
    resultados: list[dict[str, Any]] = []
    for ano in anos:
        arquivo = _melhor_arquivo(downloads, f"inf_mensal_fii_{ano}*.zip")
        if not arquivo:
            resultados.append({"ano": ano, "status": "AUSENTE", "tipo": "mensal"})
            continue

        existentes = _registros_mensais_existentes(ano)
        if existentes and not force:
            resultados.append(
                {
                    "ano": ano,
                    "status": "PULADO_JA_IMPORTADO",
                    "tipo": "mensal",
                    "arquivo_zip": str(arquivo),
                    "registros_existentes": existentes,
                }
            )
            continue

        resultado = importar_zip_local(arquivo, ano=ano)
        resultado["status"] = "OK"
        resultados.append(resultado)
    return resultados


def main() -> int:
    parser = argparse.ArgumentParser(description="Pipeline local para base temporal FIIA.")
    parser.add_argument("--downloads", default=str(Path.home() / "Downloads"))
    parser.add_argument("--anos", nargs="+", type=int, default=list(range(2020, 2027)))
    parser.add_argument("--importar-mensal", action="store_true")
    parser.add_argument("--force", action="store_true", help="Reimporta mesmo que o ano ja exista no banco.")
    args = parser.parse_args()

    downloads = Path(args.downloads).expanduser().resolve()
    resumo: dict[str, Any] = {"inventario": inventariar(downloads, args.anos)}

    if args.importar_mensal:
        resumo["importacao_mensal"] = importar_mensais(downloads, args.anos, force=args.force)

    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
