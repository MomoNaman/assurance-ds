"""Ligne de commande `ads`.

  ads generer                 # data/sinistres_100k.xlsx + tables synthétiques
  ads excel "Combien de sinistres auto refusés en 2025 ?"   # routage LLM (clé requise)
  ads sql "SELECT canton, count(*) FROM sinistres GROUP BY 1" # sans LLM : garde + exécution
  ads export                  # web/public/*.json pour l'interface statique
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

DATA = Path("data")
DB = DATA / "sinistres.duckdb"
XLSX = DATA / "sinistres_100k.xlsx"
WEB = Path("web/public")


def generer_excel(xlsx: Path = XLSX):
    from .data import generer
    jeu = generer()
    xlsx.parent.mkdir(parents=True, exist_ok=True)
    df = jeu.sinistres.copy()
    for c in df.columns:
        if c.startswith("date_"):
            df[c] = df[c].dt.date
    t = time.time()
    df.to_excel(xlsx, index=False, sheet_name="sinistres", engine="openpyxl")
    print(f"{xlsx} : {len(df)} lignes écrites en {time.time() - t:.0f} s")
    return jeu


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="ads")
    sp = p.add_subparsers(dest="cmd", required=True)
    sp.add_parser("generer")
    e = sp.add_parser("excel"); e.add_argument("question")
    s = sp.add_parser("sql"); s.add_argument("requete")
    x = sp.add_parser("export"); x.add_argument("--sans-excel", action="store_true",
                                                help="charger DuckDB depuis la génération plutôt que relire l'Excel")
    a = p.parse_args(argv)

    if a.cmd == "generer":
        generer_excel()
        from .excel_rag import excel_vers_duckdb
        t = time.time()
        n = excel_vers_duckdb(XLSX, DB)
        print(f"{DB} : {n} lignes chargées depuis l'Excel en {time.time() - t:.0f} s")
    elif a.cmd in ("excel", "sql"):
        from .excel_rag import Interrogateur
        from .llm import LLM
        it = Interrogateur(DB, LLM() if a.cmd == "excel" else None)
        r = it.repondre(a.question) if a.cmd == "excel" else it.executer(a.requete)
        print(json.dumps(r.__dict__, ensure_ascii=False, indent=1, default=str))
    elif a.cmd == "export":
        from .export import exporter
        exporter(WEB, DB, XLSX, relire_excel=not a.sans_excel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
